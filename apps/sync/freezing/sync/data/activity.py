import logging
from datetime import datetime, timedelta
from typing import TypeVar

import arrow
from geoalchemy2.elements import WKTElement
from sqlalchemy import and_, func, text
from sqlalchemy.orm import Session, joinedload
from stravalib import unit_helper
from stravalib.client import BatchedResultsIterator
from stravalib.exc import AccessUnauthorized, Fault, ObjectNotFound
from stravalib.model import (
    ActivityPhotoPrimary,
    DetailedActivity,
    Distance,
    SummaryActivity,
)

from freezing.model import meta
from freezing.model.orm import Athlete, Ride, RideEffort, RideError, RideGeo, RidePhoto
from freezing.sync.config import config, statsd
from freezing.sync.exc import (
    ActivityNotFound,
    CommandError,
    DataEntryError,
    IneligibleActivity,
)
from freezing.sync.utils import wktutils
from freezing.sync.utils.cache import CachingActivityFetcher

from . import BaseSync, StravaClientForAthlete

# Amount of activity overlap to permit
_overlap_ignore = timedelta(minutes=3)

T = TypeVar("T")


def _required(value: T | None, activity: SummaryActivity, field: str) -> T:
    """Narrow an activity field that Strava always sends for a ride but stravalib types as optional."""
    if value is None:
        raise DataEntryError(f"Activity {activity.id} has no {field}.")
    return value


def _start_date(activity: SummaryActivity) -> datetime:
    return _required(activity.start_date, activity, "start_date")


def _end_date(activity: SummaryActivity) -> datetime:
    elapsed = _required(activity.elapsed_time, activity, "elapsed_time")
    return _start_date(activity) + elapsed.timedelta()


def _distance(activity: SummaryActivity) -> Distance:
    return _required(activity.distance, activity, "distance")


class ActivitySync(BaseSync):
    name = "sync-activity"
    description = "Sync activities."

    def _seconds_from_duration(self, value):
        """
        Normalize a duration-like value to seconds.

        Accepts stravalib Duration (with .timedelta()), builtin datetime.timedelta,
        or any object with .total_seconds(). Falls back to int(value) if applicable.
        """
        if value is None:
            return None
        # stravalib Duration
        if hasattr(value, "timedelta") and callable(value.timedelta):
            return int(value.timedelta().total_seconds())
        # builtin timedelta or any object exposing total_seconds()
        if hasattr(value, "total_seconds") and callable(value.total_seconds):
            return int(value.total_seconds())
        # numeric seconds
        try:
            return int(value)
        except Exception:
            return None

    # sometimes this is a SummaryActivity, sometimes it's a DetailedActivity 8(
    def update_ride_basic(self, strava_activity: SummaryActivity, ride: Ride):
        """
        Set basic ride properties from the Strava Activity object.

        :param strava_activity: The Strava Activity
        :param ride: The ride model object.
        """
        # Should apply to both new and preexisting rides ...

        ride.name = strava_activity.name
        ride.start_date = strava_activity.start_date_local

        # We need to round so that "1.0" miles in data is "1.0" miles when we convert back from meters.
        # The stravalib Distance/Velocity objects carry their SI unit, which unit_helper reads.
        ride.distance = round(
            unit_helper.miles(_distance(strava_activity)).magnitude, 3
        )

        average_speed = _required(
            strava_activity.average_speed, strava_activity, "average_speed"
        )
        ride.average_speed = unit_helper.mph(average_speed).magnitude

        max_speed = _required(strava_activity.max_speed, strava_activity, "max_speed")
        ride.maximum_speed = unit_helper.mph(max_speed).magnitude
        ride.elapsed_time = self._seconds_from_duration(strava_activity.elapsed_time)
        ride.moving_time = self._seconds_from_duration(strava_activity.moving_time)

        # is it a detailed activity....
        if hasattr(strava_activity, "description"):
            ride.description = (
                strava_activity.description[-1024:]
                if strava_activity.description
                else None
            )
        if hasattr(strava_activity, "average_temp"):
            # It's Celsius as an integer... Such accuracy.
            ride.average_temp = (
                int(unit_helper.c2f(strava_activity.average_temp))
                if strava_activity.average_temp
                else None
            )

        location_parts = []
        if strava_activity.location_city:
            location_parts.append(strava_activity.location_city)
        if strava_activity.location_state:
            location_parts.append(strava_activity.location_state)
        location_str = ", ".join(location_parts)

        ride.location = location_str

        ride.private = bool(strava_activity.private)
        ride.visibility = strava_activity.visibility

        ride.commute = strava_activity.commute
        ride.ride_type = (
            strava_activity.sport_type.root if strava_activity.sport_type else None
        )

        elevation_gain = _required(
            strava_activity.total_elevation_gain,
            strava_activity,
            "total_elevation_gain",
        )
        ride.elevation_gain = int(unit_helper.feet(elevation_gain).magnitude)

        # Timezone.timezone() is None for a zone name pytz does not know.
        tz = strava_activity.timezone.timezone() if strava_activity.timezone else None
        if tz is None:
            raise DataEntryError("Activities cannot have null timezone.")
        ride.timezone = tz.zone

        if ride.photos_fetched is None and strava_activity.total_photo_count:
            ride.photos_fetched = False

        # # Short-circuit things that might result in more obscure db errors later.
        if ride.elapsed_time is None:
            raise DataEntryError("Activities cannot have null elapsed time.")

        if ride.moving_time is None:
            raise DataEntryError("Activities cannot have null moving time.")

        if ride.distance is None:
            raise DataEntryError("Activities cannot have null distance.")

        self.logger.debug(
            'Writing ride for {athlete!r}: "{ride!r}" on {date}'.format(
                athlete=ride.athlete.name,
                ride=ride.name,
                date=ride.start_date.strftime("%m/%d/%y"),
            )
        )

    def write_ride_efforts(self, strava_activity: DetailedActivity, ride: Ride):
        """Write out all effort associated with a ride to the database.

        :param strava_activity: The :class:`stravalib.orm.Activity` that is associated with this effort.
        :param ride: The db model object for ride.
        """
        session = meta.scoped_session()

        try:
            # Start by removing any existing segments for the ride.
            session.execute(
                RideEffort.__table__.delete().where(
                    RideEffort.ride_id == strava_activity.id
                )
            )

            # Then add them back in
            for se in strava_activity.segment_efforts or []:
                pr = next(
                    (ach.rank for ach in se.achievements or [] if ach.type == "pr"),
                    None,
                )
                legend = next(
                    (
                        ach.rank == 1
                        for ach in se.achievements or []
                        if ach.type == "segment_effort_count_leader"
                    ),
                    False,
                )

                if se.segment is None:
                    raise DataEntryError(
                        f"Segment effort {se.id} of activity {strava_activity.id} has no segment."
                    )
                effort = RideEffort(
                    id=se.id,
                    ride_id=strava_activity.id,
                    elapsed_time=self._seconds_from_duration(se.elapsed_time),
                    segment_name=se.segment.name,
                    segment_id=se.segment.id,
                    personal_record=pr,
                    local_legend=legend,
                )

                self.logger.debug(
                    "Writing ride effort: {se_id}: {effort!r}".format(
                        se_id=se.id, effort=effort.segment_name
                    )
                )

                session.add(effort)
                session.flush()

            # It would appear that Strava has some delayed consistency. Sometimes, no efforts are returned
            # and sometimes partial attempts are returned, so use an exponential backoff to re-fetch every
            # activity at least _MAX_EFFORT_RESYNCS times over an extended period of time.
            _MAX_EFFORT_RESYNCS = 3

            sync_count = ride.resync_count or 0
            if sync_count > _MAX_EFFORT_RESYNCS:
                ride.efforts_fetched = True
            else:
                ride.resync_count = 1 + sync_count
                ride.resync_date = datetime.now() + timedelta(
                    hours=6**sync_count
                )  # 1, 6, 36 hours

        except Exception:
            self.logger.exception(f"Error adding effort for ride: {ride}")
            raise

    def _make_photo_from_native(
        self, activity_photo: ActivityPhotoPrimary, ride: Ride, session: Session
    ) -> None:
        """Write a data native (source=1) primary photo to db.

        :param activity_photo: The primary photo from an activity.
        :param ride: The db model object for ride.
        """
        # 'photos': {u'count': 1,  # noqa: E800 (example of Strava's photo data)
        #   u'primary': {u'id': None,
        #    u'source': 1,
        #    u'unique_id': u'35453b4b-0fc1-46fd-a824-a4548426b57d',
        #    u'urls': {u'100': u'https://dgtzuqphqg23d.cloudfront.net/Vvm_Mcfk1SP-VWdglQJImBvKzGKRJrHlNN4BqAqD1po-128x96.jpg',
        #     u'600': u'https://dgtzuqphqg23d.cloudfront.net/Vvm_Mcfk1SP-VWdglQJImBvKzGKRJrHlNN4BqAqD1po-768x576.jpg'}},
        #   u'use_primary_photo': False},

        if not activity_photo.urls:
            self.logger.warning(
                f"Photo {activity_photo} present, but has no URLs (skipping)"
            )
            return

        photo = session.get(RidePhoto, activity_photo.unique_id)
        if photo:
            # keep the existing photo because we may have captions and things from the
            # secondary photo sync phase.
            photo.primary = True
            photo.img_l = photo.img_l or activity_photo.urls["600"]
        else:
            photo = RidePhoto()
            photo.id = activity_photo.unique_id
            photo.primary = True
            photo.source = activity_photo.source
            photo.ref = None
            photo.caption = None
            photo.img_l = activity_photo.urls["600"]
            photo.img_t = activity_photo.urls["100"]
            photo.ride_id = ride.id
            session.add(photo)

            self.logger.debug(f"Creating (primary) native ride photo: {photo}")

        session.flush()

    def write_ride_photo_primary(self, strava_activity: DetailedActivity, ride: Ride):
        """
        Store primary photo for activity from the main detail-level activity.

        :param strava_activity: The Strava :class:`stravalib.orm.Activity` object.
        :type strava_activity: :class:`stravalib.orm.Activity`

        :param ride: The db model object for ride.
        :type ride: bafs.orm.Ride
        """
        session = meta.scoped_session()

        primary_activity_photo = (
            strava_activity.photos.primary if strava_activity.photos else None
        )

        # Start by unprimarying any stale primary photos for this ride. Photo sync will
        # take care of physically deleting any deleted photos.
        primary_photos = session.query(RidePhoto).filter_by(
            ride_id=strava_activity.id, primary=True
        )
        for primary_photo in primary_photos:
            if (
                not primary_activity_photo
                or primary_activity_photo.unique_id != primary_photo.id
            ):
                primary_photo.primary = False
                session.flush()

        if primary_activity_photo:
            self._make_photo_from_native(primary_activity_photo, ride, session)

    def sync_rides_detail(
        self,
        athlete_id: int | None = None,
        activity_id: int | None = None,
        rewrite: bool = False,
        max_records: int | None = None,
        use_cache: bool = True,
        only_cache: bool = False,
    ):
        session = meta.scoped_session()

        q = session.query(Ride)
        q = q.options(joinedload(Ride.athlete))

        # TODO: Construct a more complex query to catch photos_fetched=False, track_fetched=False, etc.
        q = q.filter(Ride.private == False)  # noqa: E712

        if not rewrite:
            no_detail = Ride.detail_fetched == False  # noqa: E712
            resync_efforts = (Ride.efforts_fetched == False) & (  # noqa: E712
                Ride.resync_date <= datetime.now()
            )
            q = q.filter(no_detail | resync_efforts)

        if athlete_id:
            self.logger.info(f"Filtering activity details for {athlete_id}")
            q = q.filter(Ride.athlete_id == athlete_id)

        if activity_id:
            q = q.filter(Ride.id == activity_id)

        if max_records:
            self.logger.info(f"Limiting to {max_records} records")
            q = q.limit(max_records)

        use_cache = use_cache or only_cache

        self.logger.info(f"Fetching details for {q.count()} activities")

        for ride in q:
            try:
                client = StravaClientForAthlete(ride.athlete)

                af = CachingActivityFetcher(
                    cache_basedir=config.STRAVA_ACTIVITY_CACHE_DIR, client=client
                )

                # If I already fetched this ride then this is a resync looking for missing data so bypass the cache
                bypass_cache = ride.detail_fetched

                strava_activity = af.fetch(
                    athlete_id=ride.athlete_id,
                    object_id=ride.id,
                    use_cache=use_cache and not bypass_cache,
                    only_cache=only_cache,
                )

                self.update_ride_complete(strava_activity=strava_activity, ride=ride)

                session.commit()

            except Exception:
                self.logger.exception(
                    "Error fetching/writing activity detail {}, athlete {}".format(
                        ride.id, ride.athlete
                    )
                )
                session.rollback()

    def delete_activity(self, *, athlete_id: int, activity_id: int):
        session = meta.scoped_session()
        ride = (
            session.query(Ride)
            .filter(Ride.id == activity_id)
            .filter(Ride.athlete_id == athlete_id)
            .one_or_none()
        )
        if ride:
            session.delete(ride)
            session.commit()
        else:
            self.logger.warning(
                "Unable to find ride {} for athlete {} to remove.".format(
                    activity_id, athlete_id
                )
            )

    def fetch_and_store_activity_detail(
        self, *, athlete_id: int, activity_id: int, use_cache: bool = False
    ):
        with meta.transaction_context() as session:
            self.logger.info(
                "Fetching detailed activity athlete_id={}, activity_id={}".format(
                    athlete_id, activity_id
                )
            )

            athlete = session.get(Athlete, athlete_id)
            if not athlete:
                self.logger.warning(
                    "Athlete {} not found in database, ignoring activity {}".format(
                        athlete_id, activity_id
                    )
                )
                return

            try:
                client = StravaClientForAthlete(athlete)

                af = CachingActivityFetcher(
                    cache_basedir=config.STRAVA_ACTIVITY_CACHE_DIR, client=client
                )

                strava_activity = af.fetch(
                    athlete_id=athlete_id,
                    object_id=activity_id,
                    use_cache=use_cache,
                )

                self.check_activity(
                    strava_activity,
                    start_date=config.START_DATE,
                    end_date=config.END_DATE,
                    exclude_keywords=config.EXCLUDE_KEYWORDS,
                )

                self.check_db_overlap(
                    strava_activity,
                )

                ride = self.write_ride(strava_activity)
                self.update_ride_complete(strava_activity=strava_activity, ride=ride)
            except ObjectNotFound as e:
                raise ActivityNotFound(
                    f"Activity {activity_id} not found, ignoring."
                ) from e
            except IneligibleActivity:
                raise
            except AccessUnauthorized:
                self.logger.error(
                    f"Invalid authorization token for {athlete} (removing)"
                )
                athlete.access_token = None
            except Fault as x:
                self.logger.exception(
                    "Stravalib fault: "
                    "detail {}, athlete {}, exception {}".format(
                        activity_id, athlete_id, str(x)
                    )
                )
                raise
            except Exception:
                self.logger.exception(
                    "Error fetching/writing activity "
                    "detail {}, athlete {}".format(activity_id, athlete_id)
                )
                raise

    def update_ride_complete(self, strava_activity: DetailedActivity, ride: Ride):
        """Update all ride data from a fully-populated Strava `Activity`.

        :param strava_activity: The Activity that has been populated from detailed fetch.
        :param ride: The database ride object to update.
        """
        session = meta.scoped_session()

        # We do this just to take advantage of the use-cache/only-cache feature for reprocessing activities.
        self.update_ride_basic(strava_activity=strava_activity, ride=ride)
        session.flush()
        try:
            self.logger.info(f"Writing out efforts for {ride!r}")
            self.write_ride_efforts(strava_activity, ride)
            session.flush()
        except Exception:
            self.logger.error(
                "Error writing efforts for activity {}, athlete {}".format(
                    ride.id, ride.athlete
                ),
                exc_info=self.logger.isEnabledFor(logging.DEBUG),
            )
            raise
        try:
            if strava_activity.total_photo_count and not ride.private:
                self.logger.info(f"Writing out primary photo for {ride!r}")
                self.write_ride_photo_primary(strava_activity, ride)
            else:
                self.logger.debug(f"No photos for {ride!r}")
        except Exception:
            self.logger.error(
                "Error writing primary photo for activity {}, athlete {}".format(
                    ride.id, ride.athlete
                ),
                exc_info=self.logger.isEnabledFor(logging.DEBUG),
            )
            raise
        ride.detail_fetched = True
        # We don't get events when photo descriptions are updated, so instead
        # every time we fetch the details we schedule a photo fetch. This will
        # trigger alongside our automatic ride-effort re-sync. We don't gate
        # this on activity.total_photo_count because if someone deletes their
        # photos in Strava we probably want to resync and delete our photos.
        ride.photos_fetched = False

    def check_activity(
        self,
        activity: DetailedActivity,
        *,
        start_date: datetime,
        end_date: datetime,
        exclude_keywords: list[str] | None,
    ):
        """Assert that activity is valid for the competition.

        :param activity:
        :param start_date:
        :param end_date:
        :param exclude_keywords:
        :return:
        """
        assert end_date.tzinfo, "Need timezone-aware end date."
        assert start_date.tzinfo, "Need timezone-aware start date"

        if exclude_keywords is None:
            exclude_keywords = []

        activity_end_date = _end_date(activity)
        if start_date and _start_date(activity) < start_date:
            raise IneligibleActivity(
                "Skipping ride {} ({!r}) because date ({}) is before competition start date ({})".format(
                    activity.id, activity.name, activity.start_date, start_date
                )
            )

        if end_date and activity_end_date > end_date:
            raise IneligibleActivity(
                "Skipping ride {} ({!r}) because date ({}) is after competition end date ({})".format(
                    activity.id, activity.name, activity_end_date, end_date
                )
            )

        if activity.type not in ("Ride", "EBikeRide"):
            raise IneligibleActivity(
                "Skipping {} activity {} ({!r}) because it is not a RIDE or EBIKERIDE.".format(
                    activity.type, activity.id, activity.name
                )
            )

        if activity.trainer:
            raise IneligibleActivity(
                "Skipping ride {} ({!r}) because it is a trainer ride.".format(
                    activity.id, activity.name
                )
            )

        if activity.manual:
            raise IneligibleActivity(
                "Skipping ride {} ({!r}) because it is a manually entered ride.".format(
                    activity.id, activity.name
                )
            )

        activity_name = (activity.name or "").lower()
        for keyword in exclude_keywords:
            if keyword.lower() in activity_name:
                raise IneligibleActivity(
                    "Skipping ride {} ({!r}) due to presence of exclusion keyword: {!r}".format(
                        activity.id, activity.name, keyword
                    )
                )

    # Reject any rides that overlap with existing rides in the database, mostly to skip when
    # riders use multiple devices and forget to delete the duplicate activities. This will
    # cause problems for riders who hand-edit activities. In particular, if you slice the
    # start and end off a ride and join those both into one ride, that will overlap the main
    # part of the ride and one will be excluded. Just upload three rides instead.
    # Allow some overlap at the start end, just in case .. things.
    # Use local time because that's what is stored in the database.
    def check_db_overlap(
        self,
        activity: DetailedActivity,
    ):
        athlete = _required(activity.athlete, activity, "athlete")
        start_date_local = _required(
            activity.start_date_local, activity, "start_date_local"
        )
        elapsed_time = _required(activity.elapsed_time, activity, "elapsed_time")
        overlaps = (
            meta.scoped_session()
            .execute(
                text("""
                      select R.id
                      from rides R
                      where R.athlete_id = :athlete_id
                      and R.id != :activity_id
                      and R.start_date <= :end_date
                      AND DATE_ADD(R.start_date, INTERVAL R.elapsed_time SECOND) >= :start_date
                      AND R.name not like '%#nooverlap%'
                    """).bindparams(
                    athlete_id=athlete.id,
                    activity_id=activity.id,
                    start_date=start_date_local + _overlap_ignore,
                    end_date=(
                        start_date_local + elapsed_time.timedelta() - _overlap_ignore
                    ),
                ),
            )
            .fetchall()
        )
        if overlaps and "#nooverlap" not in (activity.name or "").lower():
            ride_ids = ", ".join(str(r[0]) for r in overlaps)
            raise IneligibleActivity(
                f"Skipping ride {activity.id} because it overlaps with existing ride {ride_ids}."
            )

    def list_rides(
        self,
        athlete: Athlete,
        start_date: datetime,
        end_date: datetime,
        exclude_keywords: list[str] | None = None,
    ) -> list[SummaryActivity]:
        """
        List all of the rides for individual athlete.

        :param athlete: The Athlete model object.
        :param start_date: The date to start listing rides.

        :param exclude_keywords: A list of keywords to use for excluding rides from the results (e.g. "#NoBAFS")

        :return: list of activity objects for rides in reverse chronological order.
        """
        try:
            client = StravaClientForAthlete(athlete)
        except Fault as x:
            self.logger.warning(str(x))
            raise

        def is_excluded(activity):
            try:
                self.check_activity(
                    activity,
                    start_date=start_date,
                    end_date=end_date,
                    exclude_keywords=exclude_keywords,
                )
            except IneligibleActivity as x:
                self.logger.info(str(x))
                return True
            else:
                return False

        activities: BatchedResultsIterator[SummaryActivity] = client.get_activities(
            after=start_date, limit=None
        )

        filtered_rides = [
            a
            for a in activities
            if (
                (a.type == "Ride" or a.type == "EBikeRide")
                and not a.manual
                and not a.trainer
                and not is_excluded(a)
            )
        ]

        # If this rider has overlapping rides, just select the largest ride. This is because when
        # we run a full sync the database may be empty so we pull all rides from Strava then filter
        # and then insert, so filtering can't look at the database.
        def overlaps_larger(
            activity: SummaryActivity, activities: list[SummaryActivity]
        ):
            overlaps = [
                a
                for a in activities
                if a.id != activity.id
                and "#nooverlap" not in (a.name or "").lower()
                and _distance(a) > _distance(activity)
                and _start_date(a) + _overlap_ignore <= _end_date(activity)
                and _end_date(a) >= _start_date(activity) + _overlap_ignore
            ]
            if overlaps and "#nooverlap" not in (activity.name or "").lower():
                overlap_ids = ", ".join([str(a.id) for a in overlaps])
                self.logger.info(
                    f"Excluding ride {activity.id} because of overlap with {overlap_ids}"
                )
                return True
            return False

        return [a for a in filtered_rides if not overlaps_larger(a, filtered_rides)]

    def write_ride(self, activity: SummaryActivity) -> Ride:
        """Take the specified activity and write it to the database.

        :param activity: The Strava :class:`stravalib.orm.Activity` object.

        :return: A tuple including the written Ride model object, whether to resync segment efforts, and whether to resync photos.
        :rtype: bafs.orm.Ride
        """
        session = meta.scoped_session()
        with session.no_autoflush:
            if activity.start_latlng:
                start_geo = WKTElement(
                    wktutils.point_wkt(
                        activity.start_latlng.lon, activity.start_latlng.lat
                    )
                )
            else:
                start_geo = None

            if activity.end_latlng:
                end_geo = WKTElement(
                    wktutils.point_wkt(activity.end_latlng.lon, activity.end_latlng.lat)
                )
            else:
                end_geo = None

            athlete_id = _required(activity.athlete, activity, "athlete").id

            # Fail fast for invalid data (this can happen with manual-entry rides)
            assert activity.elapsed_time is not None
            assert activity.moving_time is not None
            assert activity.distance is not None

            # Find the model object for that athlete (or create if doesn't exist)
            athlete = session.get(Athlete, athlete_id)
            if not athlete:
                # The athlete has to exist since otherwise we wouldn't be able to query their rides
                raise ValueError(
                    "Somehow you are attempting to write rides for an athlete not found in the database."
                )

            if start_geo is not None or end_geo is not None:
                ride_geo = RideGeo()
                ride_geo.start_geo = start_geo
                ride_geo.end_geo = end_geo
                ride_geo.ride_id = activity.id
                session.merge(ride_geo)

            ride = session.get(Ride, activity.id)
            new_ride = ride is None

            if new_ride:
                ride = Ride(activity.id)

                # Set the "workflow flags".  These all default to False in the database.  The value of NULL means
                # that the workflow flag does not apply (e.g. do not bother fetching this)

                ride.detail_fetched = False  # Just to be explicit

                ride.track_fetched = False

                # update_ride_basic will do this anyway
                if activity.total_photo_count:
                    ride.photos_fetched = False

                session.add(ride)

            else:
                # If ride has been cropped, we re-fetch it.
                if round(ride.distance, 3) != round(
                    unit_helper.miles(activity.distance.quantity()).magnitude, 3
                ):
                    self.logger.info(
                        "Queing resync of details for activity {!r}: "
                        "distance mismatch ({} != {})".format(
                            activity,
                            ride.distance,
                            unit_helper.miles(activity.distance).magnitude,
                        )
                    )
                    ride.detail_fetched = False
                    ride.track_fetched = False

            ride.athlete = athlete

            self.update_ride_basic(strava_activity=activity, ride=ride)

        if new_ride:
            statsd.histogram("strava.activity.distance", ride.distance)

        return ride

    def _sync_rides(
        self, start_date: datetime, end_date: datetime, athlete, rewrite: bool = False
    ):
        sess = meta.scoped_session()

        api_ride_entries = self.list_rides(
            athlete=athlete,
            start_date=start_date,
            end_date=end_date,
            exclude_keywords=config.EXCLUDE_KEYWORDS,
        )

        # Because MySQL doesn't like it and we are not storing tz info in the db.
        start_notz = start_date.replace(tzinfo=None)

        q = sess.query(Ride)
        q = q.filter(and_(Ride.athlete_id == athlete.id, Ride.start_date >= start_notz))
        db_rides = q.all()

        # Quickly filter out only the rides that are not in the database.
        returned_ride_ids = {r.id for r in api_ride_entries}
        db_rides_by_id = {r.id: r for r in db_rides}
        stored_ride_ids = set(db_rides_by_id.keys())
        removed_ride_ids = list(stored_ride_ids - returned_ride_ids)

        num_rides = len(api_ride_entries)

        ride_ids_needing_detail = []
        ride_ids_needing_streams = []

        for i, strava_activity in enumerate(api_ride_entries):
            self.logger.debug(
                "Processing ride: {} ({}/{})".format(
                    strava_activity.id, i + 1, num_rides
                )
            )

            if rewrite or strava_activity.id not in stored_ride_ids:
                try:
                    ride = self.write_ride(strava_activity)
                    self.logger.info(
                        "[NEW RIDE]: {id} {name!r} ({i}/{num}) ".format(
                            id=strava_activity.id,
                            name=strava_activity.name,
                            i=i + 1,
                            num=num_rides,
                        )
                    )
                    sess.commit()
                except Exception as x:
                    self.logger.info(x)
                    self.logger.debug(
                        "Error writing out ride, will attempt to add/update RideError: {}".format(
                            strava_activity.id
                        )
                    )
                    sess.rollback()
                    try:
                        ride_error = sess.get(RideError, strava_activity.id)
                        if ride_error is None:
                            self.logger.exception(
                                "[ERROR] Unable to write ride (skipping): {}".format(
                                    strava_activity.id
                                )
                            )
                            ride_error = RideError()
                        else:
                            # We already have a record of the error, so log that message with less verbosity.
                            self.logger.warning(
                                "[ERROR] Unable to write ride (skipping): {}".format(
                                    strava_activity.id
                                )
                            )

                        ride_error.athlete_id = athlete.id
                        ride_error.id = strava_activity.id
                        ride_error.name = strava_activity.name
                        ride_error.start_date = strava_activity.start_date_local
                        ride_error.reason = str(x)[:1024]
                        ride_error.last_seen = datetime.now()  # FIXME: TZ?
                        sess.add(ride_error)

                        sess.commit()
                    except Exception:
                        self.logger.exception("Error adding ride-error entry.")
                else:
                    try:
                        # If there is an error entry, then we should remove it.
                        q = sess.query(RideError)
                        q = q.filter(RideError.id == ride.id)
                        deleted = q.delete(synchronize_session=False)
                        if deleted:
                            self.logger.info(
                                "Removed matching error-ride entry for {}".format(
                                    strava_activity.id
                                )
                            )
                        sess.commit()
                    except Exception:
                        self.logger.exception("Error maybe-clearing ride-error entry.")

                    if ride.detail_fetched is False:
                        ride_ids_needing_detail.append(ride.id)

                    if ride.track_fetched is False:
                        ride_ids_needing_streams.append(ride.id)

            else:
                ride = db_rides_by_id[strava_activity.id]
                strava_miles = round(
                    unit_helper.miles(_distance(strava_activity)).magnitude, 3
                )
                if round(ride.distance, 3) != strava_miles:
                    self.logger.info(
                        "[DISTANCE CHANGED]: {id} {name!r} stored={stored} strava={strava}".format(
                            id=strava_activity.id,
                            name=strava_activity.name,
                            stored=ride.distance,
                            strava=strava_miles,
                        )
                    )
                    ride.track_fetched = False
                    ride.detail_fetched = False
                    sess.commit()
                else:
                    self.logger.debug(
                        "[SKIPPED EXISTING]: {id} {name!r} ({i}/{num}) ".format(
                            id=strava_activity.id,
                            name=strava_activity.name,
                            i=i + 1,
                            num=num_rides,
                        )
                    )

        # Remove any rides that are in the database for this athlete that were not in the returned list.
        if removed_ride_ids:
            q = sess.query(Ride)
            q = q.filter(Ride.id.in_(removed_ride_ids))
            deleted = q.delete(synchronize_session=False)
            self.logger.info(
                "Removed {} no longer present rides for athlete {}.".format(
                    deleted, athlete
                )
            )
        else:
            self.logger.debug(f"(No removed rides for athlete {athlete}.)")

        sess.commit()

    def sync_rides_distributed(
        self,
        total_segments: int,
        segment: int,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ):
        """Sync rides for the athletes in one of ``total_segments`` segments.

        :param total_segments: The number of segments to divide athletes into (e.g. 24 if this is being run hourly)
        :param segment: Which segment (0-based) to select.
        :param start_date: Will default to competition start.
        :param end_date: Will default to competition end.
        """
        with meta.transaction_context() as sess:
            q = sess.query(Athlete)
            q = q.filter(Athlete.access_token is not None)
            q = q.filter(func.mod(Athlete.id, total_segments) == segment)
            athletes: list[Athlete] = q.all()
            self.logger.info(
                "Selecting segment {} / {}, found {} athletes".format(
                    segment, total_segments, len(athletes)
                )
            )
            athlete_ids = [a.id for a in athletes]
            if athlete_ids:
                return self.sync_rides(
                    start_date=start_date, end_date=end_date, athlete_ids=athlete_ids
                )
            return None

    def sync_rides(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        rewrite: bool = False,
        force: bool = False,
        athlete_ids: list[int] | None = None,
    ):
        with meta.transaction_context() as sess:
            if start_date is None:
                start_date = config.START_DATE

            if end_date is None:
                end_date = config.END_DATE

            if start_date > arrow.now():
                return

            self.logger.debug(
                "Fetching rides newer than {} and older than {}".format(
                    start_date, end_date
                )
            )

            if (arrow.now() > (end_date + config.UPLOAD_GRACE_PERIOD)) and not force:
                raise CommandError(
                    "Current time is after competition end date + grace "
                    "period, not syncing rides. (Use `force` to override.)"
                )

            if rewrite:
                self.logger.info("Rewriting existing ride data.")

            # We iterate over all of our athletes that have access tokens.  (We can't fetch anything
            # for those that don't.)
            q = sess.query(Athlete)
            q = q.filter(Athlete.access_token is not None)

            if athlete_ids is not None:
                q = q.filter(Athlete.id.in_(athlete_ids))

            # Also only fetch athletes that have teams configured.  This may not be strictly necessary
            # but this is a team competition, so not a lot of value in pulling in data for those
            # without teams.
            # (The way the athlete sync works, athletes will only be configured for a single team
            # that is one of the configured competition teams.)
            q = q.filter(Athlete.team_id is not None)

            for athlete in q.all():
                assert isinstance(athlete, Athlete)
                self.logger.info(f"Fetching rides for athlete: {athlete}")
                try:
                    self._sync_rides(
                        start_date=start_date,
                        end_date=end_date,
                        athlete=athlete,
                        rewrite=rewrite,
                    )
                except AccessUnauthorized:
                    self.logger.error(
                        f"Invalid authorization token for {athlete} (removing)"
                    )
                    athlete.access_token = None
                    sess.add(athlete)
                    sess.commit()
                except Exception:
                    self.logger.exception(f"Error syncing rides for athlete {athlete}")
                    sess.rollback()
                else:
                    sess.commit()
