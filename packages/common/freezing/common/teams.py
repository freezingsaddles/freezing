"""
Match a Strava athlete's clubs to the competition's teams.

This used to be duplicated in freezing-web and freezing-sync; see
https://github.com/freezingsaddles/freezing-web/issues/66.
"""

import logging
from collections.abc import Iterable

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

    Sets ``athlete_model.team`` to the created or updated team. The team row is
    added to the current scoped session but not committed; the caller owns the
    transaction.

    :param strava_athlete: The athlete returned by ``stravalib``'s
        ``Client.get_athlete()``; only ``id``, ``firstname``, ``lastname`` and
        ``clubs`` are used.
    :param athlete_model: The athlete's database row.
    :param competition_teams: Strava club ids of every team in the competition,
        observers included.
    :param observer_teams: Club ids of teams excluded from the leaderboard.
        Membership of one of these does not count as a conflict with a real
        team.
    :param main_team: The club everyone joins; used as a fallback when the
        athlete is in no other configured team.
    :raise MultipleTeamsError: if the athlete is in more than one real team.
    :raise NoTeamsError: if no configured team matches.
    """
    competition_teams = set(competition_teams)
    observer_teams = set(observer_teams)
    logger.info("Checking %r against %r", strava_athlete.clubs, competition_teams)

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

    matches = [c for c in strava_athlete.clubs if c.id in competition_teams]
    logger.debug("Matched: %r", matches)
    athlete_model.team = None
    if len(matches) > 1:
        # You can be on multiple teams as long as only one is a real team.
        matches = [c for c in matches if c.id not in observer_teams]
    if len(matches) > 1:
        logger.info("Multiple teams matched for %s: %s", strava_athlete, matches)
        raise MultipleTeamsError(matches)
    if not matches:
        # Fall back to the main team if it is the only team they are in.
        matches = [c for c in strava_athlete.clubs if c.id == main_team]
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
    session = meta.scoped_session()
    team = session.get(Team, club.id)
    if team is None:
        team = Team()
    team.id = club.id
    team.name = club.name
    team.cover_photo = getattr(club, "cover_photo", None)
    team.profile_photo = getattr(club, "profile", None)
    team.leaderboard_exclude = club.id in observer_teams
    athlete_model.team = team
    session.add(team)
    return team
