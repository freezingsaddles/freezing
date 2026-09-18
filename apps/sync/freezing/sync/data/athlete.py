from datetime import datetime

from stravalib import model as sm

from freezing.common import teams
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
                self.logger.info("Limiting to {} records.".format(max_records))
                q = q.limit(max_records)

            for athlete in q.all():
                self.logger.info("Updating athlete: {0}".format(athlete))
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
                        "Error registering athlete {0}".format(athlete), exc_info=True
                    )

    def register_athlete(
        self, strava_athlete: sm.DetailedAthlete, access_token: str
    ) -> Athlete:
        """
        Ensure specified athlete is added to database, returns athlete model.

        :return: The added athlete model object.
        :rtype: :class:`bafs.model.Athlete`
        """
        session = meta.scoped_session()
        athlete = session.get(Athlete, strava_athlete.id)

        if athlete is None:
            athlete = Athlete()

        athlete.id = strava_athlete.id
        athlete_name = f"{strava_athlete.firstname} {strava_athlete.lastname}"
        athlete.profile_photo = strava_athlete.profile
        athlete.access_token = access_token

        def already_exists(display_name) -> bool:
            return (
                session.query(Athlete)
                .filter(Athlete.id != athlete.id)
                .filter(Athlete.display_name == display_name)
                .count()
                > 0
            )

        def unambiguous_display_name() -> str:
            if not strava_athlete.lastname:
                return athlete_name
            display_name = f"{strava_athlete.firstname} {strava_athlete.lastname[0]}"
            if already_exists(display_name):
                self.logger.info(
                    f"display_name '{display_name}' conflicts, using '{athlete_name}'"
                )
                return athlete_name
            return display_name

        # Only update the display name if it is either:
        # a new athlete, or the athlete name has changed
        try:
            if athlete_name != athlete.name:
                self.logger.info(
                    f"Athlete '{athlete_name}' was renamed '{athlete.name}'"
                )
                athlete.display_name = unambiguous_display_name()
        except Exception:
            self.logger.exception(
                f"Athlete name disambiguation error for {strava_athlete.id}",
                exc_info=True,
            )
            athlete.display_name = athlete_name
        finally:
            athlete.name = athlete_name
            session.add(athlete)
        return athlete

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
