from datetime import datetime, timedelta

from stravalib.client import BatchedResultsIterator
from stravalib.model import ActivityPhoto

from freezing.model import meta
from freezing.model.orm import Ride, RidePhoto
from freezing.sync.data import StravaClientForAthlete, has_strava_authorization

from . import BaseSync

BigSize = 1000
SmallSize = 200

# Strava tells us nothing when a caption is written, and riders caption minutes
# after the ride appears, so look again soon and then back off: 2, 4, 8 ... 8192
# minutes, giving up after eleven days.
FIRST_INTERVAL = timedelta(minutes=2)
MAX_FETCHES = 14

# How often the scheduler asks what has fallen due. A ride waits for the tick
# after its due time, so anything coarser than FIRST_INTERVAL quietly stretches
# the early steps of the backoff and there is no point asking for them.
POLL_INTERVAL = timedelta(minutes=1)


def schedule_fetch(ride: Ride) -> None:
    """Start the ride's photos over from the beginning of the backoff."""
    ride.photos_fetched = 0
    ride.photos_resync_date = datetime.now()


def schedule_one_more_fetch(ride: Ride) -> None:
    """Look once more without reopening the whole backoff."""
    if ride.photos_fetched is not None:
        ride.photos_resync_date = datetime.now()


def _schedule_next_fetch(ride: Ride) -> None:
    fetches = (ride.photos_fetched or 0) + 1
    if fetches >= MAX_FETCHES:
        ride.photos_fetched = MAX_FETCHES
        ride.photos_resync_date = None
    else:
        ride.photos_fetched = fetches
        ride.photos_resync_date = datetime.now() + FIRST_INTERVAL * 2 ** (fetches - 1)


class PhotoSync(BaseSync):
    name = "sync-photos"
    description = "Sync (non-primary) ride photos."

    def sync_photos(
        self,
        athlete_id: int | None = None,
        activity_id: int | None = None,
        force: bool = False,
        verbose: bool = False,
    ):
        session = meta.scoped_session()

        q = session.query(Ride.id)
        q = q.filter_by(private=False)
        q = q.filter(Ride.athlete.has(has_strava_authorization()))
        if not force:
            q = q.filter(Ride.photos_resync_date <= datetime.now())
        if athlete_id:
            q = q.filter_by(athlete_id=athlete_id)
        if activity_id:
            q = q.filter_by(id=activity_id)

        # Read the ids up front: the loop commits, and a query iterated across a
        # commit is no longer safe to read from.
        ride_ids = [row.id for row in q]
        self.logger.info(f"Fetching photos for {len(ride_ids)} activities")

        for ride_id in ride_ids:
            ride = session.get(Ride, ride_id)
            if ride is None:
                continue
            self.logger.info(f"Writing out photos for {ride!r}")
            try:
                client = StravaClientForAthlete(ride.athlete)
                big_photos = client.get_activity_photos(ride.id, size=BigSize)
                if verbose:
                    for photo in big_photos:
                        self.logger.info(f"Big photo: {str(photo)}")
                self.write_ride_photos_nonprimary(big_photos, ride, BigSize)
                # We don't display thumbnails (SmallSize) because they are too
                # small, so don't sync them anymore.
            except Exception:
                self.logger.exception(
                    "Error fetching/writing "
                    "non-primary photos activity "
                    "{}, athlete {}".format(ride.id, ride.athlete),
                    exc_info=True,
                )
                session.rollback()
                ride = session.get(Ride, ride_id)
            # A ride whose fetch keeps failing backs off like any other, rather
            # than being retried on every pass for the rest of the season.
            _schedule_next_fetch(ride)
            # Each ride stands alone: a restart mid-pass keeps what we have.
            session.commit()

    def write_ride_photos_nonprimary(
        self,
        activity_photos: BatchedResultsIterator[ActivityPhoto],
        ride: Ride,
        size: int,
    ):
        """Write out/update all photos associated with a ride to the database.

        :param activity_photos: Photos for an activity.
        :type activity_photos: list[stravalib.orm.ActivityPhoto]

        :param ride: The db model object for ride.
        :type ride: bafs.orm.Ride
        """
        photos = meta.scoped_session().query(RidePhoto).filter_by(ride_id=ride.id)
        existing_photos = {photo.id: photo for photo in photos}
        found_primary = False
        added_photo = False

        for activity_photo in activity_photos:
            if not activity_photo.urls or str(size) not in activity_photo.urls:
                self.logger.warning(
                    "Photo {} present, but has no {} URL (skipping)".format(
                        activity_photo, size
                    )
                )
                continue
            if activity_photo.caption and "#nobafs" in activity_photo.caption.lower():
                continue

            # If it's already in the db, then skip it.
            photo = existing_photos.get(activity_photo.unique_id)
            if photo:
                del existing_photos[activity_photo.unique_id]
                found_primary = found_primary or photo.primary
            else:
                self.logger.info(
                    "Adding photo {}: {}".format(
                        activity_photo.unique_id, activity_photo.caption
                    )
                )
                photo = RidePhoto(
                    id=activity_photo.unique_id,
                    ride_id=ride.id,
                    primary=False,
                )
                meta.scoped_session().add(photo)
                added_photo = True

            if size == BigSize:  # horrid, we should just remove thumbnails
                photo.img_l = activity_photo.urls.get(str(size)) or photo.img_l
            else:
                photo.img_t = activity_photo.urls.get(str(size)) or photo.img_t
            photo.caption = activity_photo.caption

            meta.scoped_session().flush()

        for deleted_photo in existing_photos.values():
            self.logger.info(f"Deleting deleted photo {deleted_photo}")
            meta.scoped_session().delete(deleted_photo)

        # Only the ride's details name its primary photo, so a change to the
        # set of photos while we have no primary is worth another look at them.
        # Asking again for a set we have already seen is not: the answer would
        # be the one we have, and the detail fetch schedules a photo fetch, so
        # the two would call to each other until the season turned.
        if (added_photo or existing_photos) and not found_primary:
            ride.detail_fetched = False
