"""Hand back authorisations from seasons whose database is long gone."""

import json
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from stravalib import Client
from stravalib.exc import AccessUnauthorized, Fault

from freezing.sync.config import Config
from freezing.sync.data import _refresh_token_rejected
from freezing.sync.exc import CommandError
from freezing.sync.utils.mysqldump import rows

from . import BaseCommand

#: Between Strava calls, so a few hundred athletes do not arrive at once.
THROTTLE = 1.0

#: Outcomes that settle an athlete for good; anything else is tried again.
SETTLED = frozenset({"deauthorized", "already-gone"})


class DeauthorizeHistoryScript(BaseCommand):
    """Deauthorize the athletes of past seasons, from their database backups.

    Strava goes on sending webhook events for anyone who has authorised the
    application, for as long as that authorisation stands, and the only way to
    stop them is to hand the authorisation back as that athlete. A season whose
    database has been wiped takes its tokens with it, but the backups still
    hold them, so this reads the athletes straight out of a mysqldump.

    Nothing here touches the competition database.
    """

    name = "deauthorize-history"

    description = "Deauthorize athletes of past seasons from their backups."

    needs_database = False

    def build_parser(self):
        parser = super().build_parser()

        parser.add_argument(
            "backups",
            nargs="+",
            type=Path,
            help="mysqldump files, plain or .xz, in any order.",
            metavar="DUMP",
        )

        parser.add_argument(
            "--yes",
            action="store_true",
            default=False,
            help="Actually deauthorize. Without it, only says what it would do.",
        )

        parser.add_argument(
            "--ledger",
            type=Path,
            default=Path("deauthorize-history.jsonl"),
            help="Where to record what has been done, so a run can be resumed.",
            metavar="FILE",
        )

        parser.add_argument(
            "--limit",
            type=int,
            help="Stop after this many athletes, to stay inside a rate limit.",
            metavar="N",
        )

        return parser

    def tokens_by_athlete(self, backups: list[Path]) -> dict[int, list[str]]:
        """Every refresh token we have held for an athlete, newest first.

        Ordered by the expiry Strava issued with the token rather than by the
        name of the file it came from, so a backup taken out of turn does not
        put a stale token first.
        """
        seen: dict[int, dict[str, int]] = defaultdict(dict)
        for backup in backups:
            if not backup.exists():
                raise CommandError(f"no such backup: {backup}")
            count = 0
            for row in rows(backup, "athletes"):
                token = row.get("refresh_token")
                if not token:
                    continue
                expires = int(row.get("expires_at") or 0)
                athlete = int(row["id"])
                seen[athlete][token] = max(seen[athlete].get(token, 0), expires)
                count += 1
            self.logger.info(f"{backup.name}: {count} athletes with a token")
        return {
            athlete: sorted(tokens, key=tokens.get, reverse=True)
            for athlete, tokens in seen.items()
        }

    def read_ledger(self, path: Path) -> dict[int, str]:
        if not path.exists():
            return {}
        done = {}
        for line in path.read_text().splitlines():
            if line.strip():
                entry = json.loads(line)
                done[entry["athlete_id"]] = entry["outcome"]
        return done

    def record(self, path: Path, athlete_id: int, outcome: str) -> None:
        with path.open("a") as ledger:
            ledger.write(
                json.dumps(
                    {
                        "athlete_id": athlete_id,
                        "outcome": outcome,
                        "at": datetime.now(UTC).isoformat(),
                    }
                )
                + "\n"
            )

    def deauthorize(self, tokens: list[str]) -> str:
        """Try an athlete's tokens, newest first, and say how it went."""
        for token in tokens:
            client = Client()
            try:
                issued = client.refresh_access_token(
                    Config.STRAVA_CLIENT_ID, Config.STRAVA_CLIENT_SECRET, token
                )
            except Fault as fault:
                if _refresh_token_rejected(fault):
                    # This one is spent. An older one may still stand.
                    continue
                raise
            time.sleep(THROTTLE)
            try:
                Client(access_token=issued["access_token"]).deauthorize()
            except AccessUnauthorized:
                return "already-gone"
            return "deauthorized"
        return "already-gone"

    def execute(self, args):
        by_athlete = self.tokens_by_athlete(args.backups)
        done = self.read_ledger(args.ledger)

        outstanding = [a for a in sorted(by_athlete) if done.get(a) not in SETTLED]
        self.logger.info(
            "{} athletes across {} backups, {} already settled, {} to do".format(
                len(by_athlete),
                len(args.backups),
                len(by_athlete) - len(outstanding),
                len(outstanding),
            )
        )

        if not args.yes:
            self.logger.info(
                f"Would deauthorize {len(outstanding)} athletes; pass --yes to do it"
            )
            return

        counts: dict[str, int] = defaultdict(int)
        for athlete_id in outstanding[: args.limit]:
            try:
                outcome = self.deauthorize(by_athlete[athlete_id])
            except Exception as x:
                # Left unsettled on purpose, so the next run comes back to it.
                self.logger.warning(f"Athlete {athlete_id}: {x}")
                outcome = "failed"
            counts[outcome] += 1
            self.logger.info(f"Athlete {athlete_id}: {outcome}")
            self.record(args.ledger, athlete_id, outcome)
            time.sleep(THROTTLE)

        self.logger.info(", ".join(f"{n} {name}" for name, n in sorted(counts.items())))
        if counts["failed"]:
            self.logger.info(f"Run again to retry the {counts['failed']} that failed.")


def main():
    DeauthorizeHistoryScript().run()


if __name__ == "__main__":
    main()
