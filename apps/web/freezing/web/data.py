"""Functions for interacting with the datastore and the strava apis."""

from freezing.common import athletes, teams
from freezing.web import config


def register_athlete(strava_athlete, token_dict):
    """
    Ensure specified athlete is added to database, returns athlete orm.

    Thin binding of :func:`freezing.common.athletes.register_athlete` that hands
    it the token trio from an OAuth exchange; see that function for the naming
    rules.
    """
    return athletes.register_athlete(
        strava_athlete,
        access_token=token_dict["access_token"],
        refresh_token=token_dict["refresh_token"],
        expires_at=token_dict["expires_at"],
    )


def register_athlete_team(strava_athlete, athlete_model):
    """
    Update db with configured team that matches the athlete's teams.

    Thin binding of :func:`freezing.common.teams.register_athlete_team` to this
    app's configuration; see that function for the rules and exceptions.
    """
    return teams.register_athlete_team(
        strava_athlete,
        athlete_model,
        competition_teams=config.COMPETITION_TEAMS,
        observer_teams=config.OBSERVER_TEAMS,
        main_team=config.MAIN_TEAM,
    )
