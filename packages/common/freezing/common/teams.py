"""
Match a Strava athlete's clubs to the competition's teams.

This used to be duplicated in freezing-web and freezing-sync; see
https://github.com/freezingsaddles/freezing-web/issues/66.
"""

import logging
from collections.abc import Iterable

from freezing.common import athletes
from freezing.model import meta
from freezing.model.orm import Athlete, Team

log = logging.getLogger(__name__)


class NoTeamsError(RuntimeError):
    """The athlete is not in any of the competition's teams."""


class MultipleTeamsError(RuntimeError):
    """The athlete is in more than one competition team."""

    def __init__(self, teams):
        super().__init__(teams)
        self.teams = teams


def fill_clubs(client, strava_athlete):
    """
    Ask Strava for the athlete's clubs when their athlete record lists none.

    The athlete record has been seen listing no clubs for a member of ours;
    the separate list of the athlete's clubs is asked for only then, so as not
    to double the calls for everyone else.

    :param client: A ``stravalib`` client authorized as the athlete.
    :param strava_athlete: That client's ``get_athlete()``.
    :return: ``strava_athlete``, its ``clubs`` filled in.
    """
    if not strava_athlete.clubs:
        strava_athlete.clubs = list(client.get_athlete_clubs())
    return strava_athlete


# A blank account can pick up a few followers or friends of its own.
BLANK_MAX_FOLLOWERS = 5


def looks_blank(strava_athlete) -> bool:
    """
    Say whether the athlete has no clubs or gear, and hardly any followers or friends.

    Signing in to Strava with Google, Apple or Facebook can make a new, empty
    account instead of using the one the rider rides with.
    """
    return not (
        strava_athlete.clubs
        or getattr(strava_athlete, "bikes", None)
        or getattr(strava_athlete, "shoes", None)
        or (getattr(strava_athlete, "follower_count", None) or 0) > BLANK_MAX_FOLLOWERS
        or (getattr(strava_athlete, "friend_count", None) or 0) > BLANK_MAX_FOLLOWERS
    )


def register_athlete_team(
    strava_athlete,
    athlete_model: Athlete,
    *,
    competition_teams: Iterable[int],
    observer_teams: Iterable[int] = (),
    main_team: int | None = None,
    logger: logging.Logger = log,
) -> Team:
    """
    Update the database with the configured team that matches the athlete's clubs.

    Sets ``athlete_model.clubs`` to every configured club the athlete is in, even
    when no team can be chosen, and ``athlete_model.team`` to the chosen one. The
    team rows are added to the current scoped session but not committed; the
    caller owns the transaction.

    :param strava_athlete: The athlete returned by ``stravalib``'s
        ``Client.get_athlete()``; only ``id``, ``firstname``, ``lastname`` and
        ``clubs`` are used.
    :param athlete_model: The athlete's database row.
    :param competition_teams: Strava club ids of the competition's teams.
    :param observer_teams: Club ids of teams outside the competition, whose
        riders are left off its leaderboards. Membership of one of these does
        not count as a conflict with a real team.
    :param main_team: The club everyone joins; used as a fallback when the
        athlete is in no other competition team, ahead of any observer team.
    :raise MultipleTeamsError: if the athlete is in more than one real team.
    :raise NoTeamsError: if no configured team matches.
    """
    was_in_a_club = athletes.in_a_club(athlete_model)
    try:
        return _choose_team(
            strava_athlete,
            athlete_model,
            competition_teams=competition_teams,
            observer_teams=observer_teams,
            main_team=main_team,
            logger=logger,
        )
    finally:
        athletes.shorten_on_joining(
            strava_athlete, athlete_model, was_in_a_club, logger=logger
        )


def _choose_team(
    strava_athlete,
    athlete_model: Athlete,
    *,
    competition_teams: Iterable[int],
    observer_teams: Iterable[int],
    main_team: int | None,
    logger: logging.Logger,
) -> Team:
    observer_teams = set(observer_teams)
    configured = set(competition_teams) | observer_teams
    logger.info("Checking %r against %r", strava_athlete.clubs, configured)

    if strava_athlete.clubs is None:
        raise NoTeamsError(
            "Athlete {} ({} {}): No clubs returned- {}. {}.".format(
                strava_athlete.id,
                strava_athlete.firstname,
                strava_athlete.lastname,
                "Full Profile Access required",
                "Please re-authorize",
            )
        )

    session = meta.scoped_session()
    teams = {
        c.id: _team(session, c, observer_teams)
        for c in strava_athlete.clubs
        if c.id in configured
    }
    athlete_model.clubs = list(teams.values())

    matches = [c for c in strava_athlete.clubs if c.id in configured]
    logger.debug("Matched: %r", matches)
    athlete_model.team = None
    # Observer teams only count for someone in no competition team.
    real = [c for c in matches if c.id not in observer_teams]
    if len(real) > 1:
        logger.info("Multiple teams matched for %s: %s", strava_athlete, real)
        raise MultipleTeamsError(real)
    if not real:
        real = [c for c in strava_athlete.clubs if c.id == main_team]
    matches = real or matches
    if not matches:
        raise NoTeamsError(
            "Athlete {} ({} {}): {} {}".format(
                strava_athlete.id,
                strava_athlete.firstname,
                strava_athlete.lastname,
                "No teams matched ours. Teams defined:",
                strava_athlete.clubs,
            )
        )

    club = matches[0]
    team = teams.get(club.id)
    if team is None:
        team = _team(session, club, observer_teams)
        athlete_model.clubs.append(team)
    athlete_model.team = team
    return team


def _team(session, club, observer_teams: set[int]) -> Team:
    """Create or update the club's row in the session."""
    team = session.get(Team, club.id)
    if team is None:
        team = Team()
    team.id = club.id
    team.name = club.name
    team.cover_photo = getattr(club, "cover_photo", None)
    team.profile_photo = getattr(club, "profile", None)
    team.leaderboard_exclude = club.id in observer_teams
    session.add(team)
    return team
