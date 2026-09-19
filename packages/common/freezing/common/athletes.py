"""
Write a Strava athlete's identity to the database.

This used to be duplicated in freezing-web and freezing-sync, and the two copies
had drifted: web wrote the athlete's full name as their display name and never
revisited it, while sync abbreviated the surname to an initial and recomputed it
whenever Strava reported a new name. Sync's is the behaviour web's own TODO
asked for; see https://github.com/freezingsaddles/freezing-web/issues/80,
https://github.com/freezingsaddles/freezing-web/issues/75 and
https://github.com/freezingsaddles/freezing-web/issues/73.
"""

import logging

from freezing.model import meta
from freezing.model.orm import Athlete

log = logging.getLogger(__name__)


def full_name(strava_athlete) -> str:
    """Return the athlete's name, leaving out a half Strava did not give us."""
    parts = (strava_athlete.firstname, strava_athlete.lastname)
    return " ".join(part.strip() for part in parts if part and part.strip())


def display_name(
    strava_athlete, athlete_model: Athlete, *, logger: logging.Logger
) -> str:
    """
    Return the leaderboard name: a first name and a last initial.

    Falls back to the full name when there is no surname to abbreviate, or when
    the abbreviated form is already another athlete's display name.
    """
    name = full_name(strava_athlete)
    first = (strava_athlete.firstname or "").strip()
    last = (strava_athlete.lastname or "").strip()
    if not first or not last:
        return name

    abbreviated = f"{first} {last[0]}"
    taken = (
        meta.scoped_session()
        .query(Athlete)
        .filter(Athlete.id != athlete_model.id)
        .filter(Athlete.display_name == abbreviated)
        .count()
    )
    if taken:
        logger.info("display_name %r conflicts, using %r", abbreviated, name)
        return name
    return abbreviated


def register_athlete(
    strava_athlete,
    *,
    access_token: str,
    refresh_token: str | None = None,
    expires_at: int | None = None,
    logger: logging.Logger = log,
) -> Athlete:
    """
    Ensure the athlete is in the database, and return their row.

    The row is added to the current scoped session but not committed; the caller
    owns the transaction.

    The display name is (re)computed for an athlete who has none, and for one
    Strava has since renamed. An athlete who has kept their name keeps the
    display name they have, which may have been set by hand.

    :param strava_athlete: The athlete returned by ``stravalib``'s
        ``Client.get_athlete()``; only ``id``, ``firstname``, ``lastname`` and
        ``profile`` are used.
    :param access_token: The athlete's current Strava access token.
    :param refresh_token: Their refresh token, when the caller has a new one.
        Left alone when omitted.
    :param expires_at: When the access token expires, when the caller has a new
        one. Left alone when omitted.
    """
    session = meta.scoped_session()
    athlete_model = session.get(Athlete, strava_athlete.id)
    if athlete_model is None:
        athlete_model = Athlete()

    athlete_model.id = strava_athlete.id
    athlete_model.profile_photo = strava_athlete.profile
    athlete_model.access_token = access_token
    if refresh_token is not None:
        athlete_model.refresh_token = refresh_token
    if expires_at is not None:
        athlete_model.expires_at = expires_at

    name = full_name(strava_athlete)
    renamed = athlete_model.name is not None and name != athlete_model.name
    if renamed:
        logger.info("Athlete %r was renamed %r", athlete_model.name, name)
    if renamed or athlete_model.display_name is None:
        try:
            athlete_model.display_name = display_name(
                strava_athlete, athlete_model, logger=logger
            )
        except Exception:
            logger.exception(
                "Athlete name disambiguation error for %s", strava_athlete.id
            )
            athlete_model.display_name = name
    athlete_model.name = name

    session.add(athlete_model)
    return athlete_model
