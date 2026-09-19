from datetime import datetime

from freezing.sync.config import config
from freezing.sync.data.athlete import AthleteSync
from freezing.sync.exc import CommandError

from . import BaseCommand


class DeauthorizeScript(BaseCommand):
    """
    Hands every athlete's authorisation back to Strava at the end of a season.

    Strava goes on sending webhook events for anyone who has authorised the
    application, for as long as that authorisation stands, and gives the
    receiver no way to refuse them one athlete at a time. Deauthorising is the
    only thing that stops them, and it has to be done as that athlete, so it
    belongs here, before the season's tokens are thrown away.
    """

    name = "deauthorize"

    description = "Deauthorize athletes from Strava at the end of the season."

    def build_parser(self):
        parser = super().build_parser()

        parser.add_argument(
            "--yes",
            action="store_true",
            default=False,
            help="Actually deauthorize. Without it, only says what it would do.",
        )

        parser.add_argument(
            "--athlete-id",
            type=int,
            help="Just this athlete, rather than everyone.",
            metavar="ID",
        )

        parser.add_argument(
            "--before-the-end",
            action="store_true",
            default=False,
            help="Allow this before END_DATE, which disconnects a live competition.",
        )

        return parser

    def execute(self, args):
        now = datetime.now(config.END_DATE.tzinfo)
        if now < config.END_DATE and not args.before_the_end:
            raise CommandError(
                "the competition runs until {}; deauthorizing now disconnects "
                "every rider from Strava mid-season. Pass --before-the-end if "
                "that is really what you want.".format(config.END_DATE)
            )

        done, failed = AthleteSync(logger=self.logger).deauthorize_athletes(
            athlete_id=args.athlete_id, commit=args.yes
        )
        if args.yes:
            self.logger.info(f"Deauthorized {done} athletes, {failed} failed")
            if failed and not done:
                raise CommandError(
                    f"not one of {failed} athletes could be deauthorized, which "
                    "looks like a problem at our end rather than theirs. No "
                    "tokens were cleared."
                )
        else:
            self.logger.info(f"Would deauthorize {done} athletes; pass --yes to do it")


def main():
    DeauthorizeScript().run()


if __name__ == "__main__":
    main()
