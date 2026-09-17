"""
Functions for interacting with the datastore and the strava apis.
"""

from __future__ import division, unicode_literals

from freezing.common import teams
from freezing.model import meta
from freezing.model.orm import Athlete
from freezing.web import config


def register_athlete(strava_athlete, token_dict):
    """
    Ensure specified athlete is added to database, returns athlete orm.

    :return: The added athlete model object.
    :rtype: :class:`bafs.orm.Athlete`
    """
    athlete = meta.scoped_session().get(Athlete, strava_athlete.id)
    if athlete is None:
        athlete = Athlete()
    athlete.id = strava_athlete.id
    athlete.name = "{0} {1}".format(
        strava_athlete.firstname, strava_athlete.lastname
    ).strip()
    # Temporary; we will update this in disambiguation phase.  (This isn't optimal; needs to be
    # refactored....
    #
    #     Where does the disambiguation phase get called now? Nowhere...
    #     so let's fix it here for now.
    #     * Do not override already set display_names.
    #     * Use a first name and last initial (if available).
    #     See also:
    #       https://github.com/freezingsaddles/freezing-web/issues/80
    #       https://github.com/freezingsaddles/freezing-web/issues/75
    #       https://github.com/freezingsaddles/freezing-web/issues/73
    #     - @obscurerichard]
    if athlete.display_name is None:
        if strava_athlete.lastname is None:
            athlete.display_name = strava_athlete.firstname
        else:
            athlete.display_name = "{0} {1}".format(
                strava_athlete.firstname.strip(),
                strava_athlete.lastname.strip(),
            )
    athlete.profile_photo = strava_athlete.profile

    athlete.access_token = token_dict["access_token"]
    athlete.refresh_token = token_dict["refresh_token"]
    athlete.expires_at = token_dict["expires_at"]
    meta.scoped_session().add(athlete)

    return athlete


def register_athlete_team(strava_athlete, athlete_model):
    """
    Updates db with configured team that matches the athlete's teams.

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
