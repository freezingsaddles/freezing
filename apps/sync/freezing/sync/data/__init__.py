import abc
import logging
import time

from sqlalchemy import or_
from stravalib import Client
from stravalib.exc import Fault

from freezing.model import meta
from freezing.model.orm import Athlete
from freezing.sync.config import Config
from freezing.sync.exc import AthleteDeauthorized


def has_strava_authorization():
    """Match the athletes we can still fetch for."""
    return or_(
        Athlete.refresh_token.isnot(None),
        Athlete.access_token.isnot(None),
    )


def forget_athlete(athlete: Athlete, logger: logging.Logger) -> None:
    """Throw away tokens Strava will not honour again."""
    logger.info(
        "athlete %s has disconnected the application, forgetting their tokens",
        athlete.id,
    )
    athlete.access_token = None
    athlete.refresh_token = None
    athlete.expires_at = 0
    meta.scoped_session().add(athlete)
    meta.scoped_session().commit()


def _refresh_token_rejected(fault: Fault) -> bool:
    """Say whether Strava refused the refresh token itself, not just the call."""
    response = getattr(fault, "response", None)
    if response is None or response.status_code != 400:
        return False
    try:
        errors = response.json().get("errors", [])
    except ValueError:
        return False
    return any(
        error.get("field") == "refresh_token" and error.get("code") == "invalid"
        for error in errors
    )


class StravaClientForAthlete(Client):
    """Creates a StravaClient for the specified athlete."""

    def __init__(
        self,
        athlete: int | Athlete,
        logger: logging.Logger | None = None,
    ):
        self.logger = logger or logging.getLogger(__name__)
        assert athlete, "No athlete ID or Athlete object provided."
        if athlete is None:
            raise ValueError("athlete may not be None")
        if not isinstance(athlete, Athlete):
            athlete_id = athlete
            athlete = meta.scoped_session().query(Athlete).get(athlete_id)
            if not athlete:
                raise ValueError(f"Athlete ID does not exist in database: {athlete_id}")
        super().__init__(access_token=athlete.access_token, rate_limit_requests=True)
        self.refresh_athlete_access_token(athlete)

    def refresh_athlete_access_token(self, athlete: Athlete):
        assert athlete, "No athlete ID or Athlete object provided."
        if athlete.refresh_token is not None:
            an_hour_from_now = time.time() + 60 * 60
            if athlete.access_token is None or athlete.expires_at < an_hour_from_now:
                refresh_token = athlete.refresh_token
                self.logger.info(
                    "access token for athlete %s is stale, expires_at=%s",
                    athlete.id,
                    athlete.expires_at,
                )
            else:
                # Access token is still valid - no action needed
                refresh_token = None
                self.logger.info(
                    "access token for athlete %s is still valid ",
                    athlete.id,
                )
        elif athlete.access_token is not None:
            # Athlete has an access token but no refresh token yet.
            # Upgrade the forever token to the new tokens as described in:
            # https://developers.strava.com/docs/oauth-updates/#migration-instructions
            refresh_token = athlete.access_token
        else:
            raise AthleteDeauthorized(
                f"athlete {athlete.id} had no access or refresh token"
            )
        if refresh_token:
            self.logger.info("refreshing access token for athlete %s", athlete.id)
            try:
                token_dict = super().refresh_access_token(
                    Config.STRAVA_CLIENT_ID,
                    Config.STRAVA_CLIENT_SECRET,
                    refresh_token,
                )
            except Fault as fault:
                if not _refresh_token_rejected(fault):
                    raise
                forget_athlete(athlete, self.logger)
                raise AthleteDeauthorized(
                    f"athlete {athlete.id} has disconnected the application"
                ) from fault
            self.access_token = token_dict["access_token"]
            athlete.access_token = token_dict["access_token"]
            athlete.refresh_token = token_dict["refresh_token"]
            athlete.expires_at = token_dict["expires_at"]
            meta.scoped_session().add(athlete)
            meta.scoped_session().commit()


class BaseSync(metaclass=abc.ABCMeta):
    @property
    @abc.abstractmethod
    def name(self):
        pass

    @property
    @abc.abstractmethod
    def description(self):
        pass

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(__name__)
