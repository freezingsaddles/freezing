from datetime import datetime

from sqlalchemy import or_
from stravalib import model as sm
from stravalib.exc import AccessUnauthorized

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

    def deauthorize_athletes(
        self, athlete_id: int | None = None, commit: bool = False
    ) -> tuple[int, int]:
        """Hand every athlete's authorisation back to Strava, and forget their tokens.

        Strava keeps sending webhook events for anyone who has authorised the
        application, and offers the receiver no way to refuse them for one
        athlete. Deauthorising is the only thing that stops them, and it has to
        be done as that athlete, so it has to happen before their tokens are
        thrown away.

        :param athlete_id: Just this athlete, rather than all of them.
        :param commit: Actually do it. Left alone, this only says what it would.
        :return: How many were deauthorised, and how many failed.
        """
        done = failed = 0
        with meta.transaction_context() as sess:
            q = sess.query(Athlete).filter(
                or_(
                    Athlete.access_token.isnot(None),
                    Athlete.refresh_token.isnot(None),
                )
            )
            if athlete_id:
                q = q.filter(Athlete.id == athlete_id)

            for athlete in q.all():
                if not commit:
                    self.logger.info(f"Would deauthorize {athlete.id} ({athlete.name})")
                    done += 1
                    continue
                try:
                    # The client refreshes the token first, so a stale one is
                    # not what makes this fail.
                    StravaClientForAthlete(athlete, logger=self.logger).deauthorize()
                    self.logger.info(f"Deauthorized {athlete.id} ({athlete.name})")
                except AccessUnauthorized as e:
                    # They revoked us at their end. There is nothing left to
                    # hand back, so the tokens go the same way as the rest.
                    self.logger.info(
                        f"Athlete {athlete.id} ({athlete.name}) had already "
                        f"disconnected, clearing tokens: {e}"
                    )
                except Exception:
                    # Anything else -- our own client credentials rejected, for
                    # one -- says nothing about this athlete's authorisation,
                    # so leave their tokens alone and let the count show it.
                    self.logger.exception(f"Could not deauthorize {athlete.id}")
                    failed += 1
                    continue
                athlete.access_token = None
                athlete.refresh_token = None
                athlete.expires_at = 0
                sess.add(athlete)
                done += 1
        return done, failed

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
