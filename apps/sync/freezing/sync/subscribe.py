import logging
import threading
from time import sleep

import greenstalk

from freezing.model import meta
from freezing.model.msg.mq import (
    ActivityUpdate,
    ActivityUpdateSchema,
    AthleteUpdate,
    AthleteUpdateSchema,
    DefinedTubes,
)
from freezing.model.msg.strava import AspectType
from freezing.model.orm import Athlete
from freezing.sync.autolog import log
from freezing.sync.config import Config, statsd
from freezing.sync.data import forget_athlete
from freezing.sync.data.activity import ActivitySync
from freezing.sync.data.photos import PhotoSync
from freezing.sync.data.streams import StreamSync
from freezing.sync.exc import (
    ActivityNotFound,
    AthleteDeauthorized,
    IneligibleActivity,
)


class ActivityUpdateSubscriber:
    def __init__(
        self, beanstalk_client: greenstalk.Client, shutdown_event: threading.Event
    ):
        self.client = beanstalk_client
        self.shutdown_event = shutdown_event
        self.logger = logging.getLogger(__name__)
        self.activity_sync = ActivitySync(self.logger)
        self.streams_sync = StreamSync(self.logger)
        self.photos_sync = PhotoSync(self.logger)

        """Delay between requests to Strava API to avoid rate limiting."""
        self._THROTTLE_DELAY = 3.0

    def handle_message(self, message: ActivityUpdate):
        self.logger.info(f"Processing activity update {message}")

        with meta.transaction_context() as session:
            athlete: Athlete = session.get(Athlete, message.athlete_id)
            if not athlete:
                self.logger.warning(
                    "Athlete {} not found in database, "
                    "ignoring activity update message {}".format(
                        message.athlete_id, message
                    )
                )
                return  # Makes the else a little unnecessary, but reads easier.
            try:
                if message.operation is AspectType.delete:
                    statsd.increment(
                        "strava.activity.delete",
                        tags=[f"team:{athlete.team_id}"],
                    )
                    self.activity_sync.delete_activity(
                        athlete_id=message.athlete_id, activity_id=message.activity_id
                    )

                elif message.operation is AspectType.update:
                    statsd.increment(
                        "strava.activity.update",
                        tags=[f"team:{athlete.team_id}"],
                    )
                    self.activity_sync.fetch_and_store_activity_detail(
                        athlete_id=message.athlete_id,
                        activity_id=message.activity_id,
                        photos_changed=True,
                    )
                    self.streams_sync.fetch_and_store_activity_streams(
                        athlete_id=message.athlete_id, activity_id=message.activity_id
                    )
                    self.photos_sync.sync_photos(
                        athlete_id=message.athlete_id,
                        activity_id=message.activity_id,
                        force=True,
                    )

                elif message.operation is AspectType.create:
                    statsd.increment(
                        "strava.activity.create",
                        tags=[f"team:{athlete.team_id}"],
                    )
                    self.activity_sync.fetch_and_store_activity_detail(
                        athlete_id=message.athlete_id, activity_id=message.activity_id
                    )
                    self.streams_sync.fetch_and_store_activity_streams(
                        athlete_id=message.athlete_id, activity_id=message.activity_id
                    )
                    self.photos_sync.sync_photos(
                        athlete_id=message.athlete_id, activity_id=message.activity_id
                    )
            except (ActivityNotFound, AthleteDeauthorized, IneligibleActivity) as x:
                log.info(str(x))

    def handle_athlete_message(self, message: AthleteUpdate):
        self.logger.info(f"Processing athlete update {message}")

        if not message.deauthorized:
            self.logger.info(f"Nothing to do for {message}")
            return

        with meta.transaction_context() as session:
            athlete: Athlete = session.get(Athlete, message.athlete_id)
            if not athlete:
                self.logger.info(
                    f"Athlete {message.athlete_id} not found in database, "
                    f"ignoring {message}"
                )
                return
            statsd.increment(
                "strava.athlete.deauthorize",
                tags=[f"team:{athlete.team_id}"],
            )
            # Their rides stay: the competition is scored on what was ridden,
            # not on who is still connected. Only the tokens go.
            forget_athlete(athlete, self.logger)

    def run_forever(self):
        # This is expecting to run in the main thread. Needs a bit of redesign
        # if this is to be moved to a background thread.
        try:
            schemas = {
                DefinedTubes.activity_update.value: (
                    ActivityUpdateSchema(),
                    self.handle_message,
                ),
                DefinedTubes.athlete_update.value: (
                    AthleteUpdateSchema(),
                    self.handle_athlete_message,
                ),
            }

            while not self.shutdown_event.is_set():
                try:
                    job = self.client.reserve(timeout=30)
                except KeyboardInterrupt, SystemExit:
                    raise
                except greenstalk.TimedOutError:
                    self.logger.debug(
                        "Internal beanstalkd connection timeout; reconnecting."
                    )
                    continue
                else:
                    try:
                        tube = self.client.stats_job(job)["tube"]
                        self.logger.info(f"Received {tube} message: {job.body!r}")
                        schema, handle = schemas[tube]
                        handle(schema.loads(job.body))
                    except Exception:
                        msg = "Error processing message, will requeue w/ delay of {} seconds."
                        self.logger.exception(msg.format(Config.REQUEUE_DELAY))
                        statsd.increment("strava.webhook.error")
                        self.client.release(
                            job, delay=Config.REQUEUE_DELAY
                        )  # We put it back with a delay
                    else:
                        self.client.delete(job)
                        # Throttle requests to avoid hitting rate limits
                        sleep(self._THROTTLE_DELAY)

        except KeyboardInterrupt, SystemExit:
            raise
        except Exception:
            self.logger.exception("Unhandled error in tube subscriber loop, exiting.")
            self.shutdown_event.set()
            raise
