from datetime import datetime

from stravalib import model as sm

from freezing.common import athletes, teams
from freezing.model import meta
from freezing.model.orm import Athlete, Team
from freezing.sync.config import config
from freezing.sync.exc import MultipleTeamsError, NoTeamsError

from . import BaseSync, StravaClientForAthlete


class AthleteSync(BaseSync):
    name = "sync-athletes"
    description = "Sync athletes."

    def all_done(self):
        loc_time = datetime.now(config.TIMEZONE)
        end_time = config.END_DATE
        return loc_time > end_time

    def sync_athletes(self, max_records: int | None = None):
        with meta.transaction_context() as sess:
            # We iterate over all of our athletes that have access tokens.
            # (We can't fetch anything for those that don't.)

            q = sess.query(Athlete)
            q = q.filter(Athlete.access_token is not None)
            if max_records:
                self.logger.info(f"Limiting to {max_records} records.")
                q = q.limit(max_records)

            for athlete in q.all():
                self.logger.info(f"Updating athlete: {athlete}")
                try:
                    client = StravaClientForAthlete(athlete)
                    strava_athlete = client.get_athlete()
                    self.register_athlete(strava_athlete, athlete.access_token)
                    if not self.all_done():
                        self.register_athlete_team(strava_athlete, athlete)
                except NoTeamsError as ex:
                    self.logger.info(
                        f'Athlete "{athlete}" is not on a registered team: {ex}'
                    )
                except MultipleTeamsError as ex:
                    self.logger.info(
                        f'Athlete "{athlete}" is on multiple competition teams: {ex}'
                    )
                except Exception:
                    self.logger.exception(
                        f"Error registering athlete {athlete}", exc_info=True
                    )

    def register_athlete(
        self, strava_athlete: sm.DetailedAthlete, access_token: str
    ) -> Athlete:
        """Ensure specified athlete is added to database, returns athlete model.

        Thin binding of :func:`freezing.common.athletes.register_athlete`. The
        client has already refreshed and stored this athlete's refresh token and
        expiry, so only the access token is passed on.
        """
        return athletes.register_athlete(
            strava_athlete, access_token=access_token, logger=self.logger
        )

    def register_athlete_team(
        self, strava_athlete: sm.DetailedAthlete, athlete_model: Athlete
    ) -> Team:
        """Update db with configured team that matches the athlete's teams.

        Thin binding of :func:`freezing.common.teams.register_athlete_team` to
        this app's configuration; see that function for the rules and
        exceptions. Commits the session either way.
        """
        try:
            return teams.register_athlete_team(
                strava_athlete,
                athlete_model,
                competition_teams=config.COMPETITION_TEAMS,
                observer_teams=config.OBSERVER_TEAMS,
                main_team=config.MAIN_TEAM,
                logger=self.logger,
            )
        finally:
            meta.scoped_session().commit()
