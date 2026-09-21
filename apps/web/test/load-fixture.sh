#!/usr/bin/env bash
#
# Load the spider's fixture and move its dates to now.
#
# The fixture is generated once and then sits in the repository, so the dates
# in it are shifted at load time rather than at generation time: the newest
# ride always lands yesterday, and the competition always has a month to run.
#
# Writes START_DATE and END_DATE to stdout as shell assignments, and to
# $GITHUB_ENV when there is one.

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

MYSQL=${MYSQL:-mysql}
HOST=${MYSQL_HOST:-127.0.0.1}
PORT=${MYSQL_PORT:-3306}
USER=${MYSQL_USER:-root}
PASSWORD=${MYSQL_PASSWORD:-test}
DATABASE=${MYSQL_DATABASE:-freezing}

# Unquoted, so MYSQL can carry arguments of its own.
# shellcheck disable=SC2086
sql() { $MYSQL -h "$HOST" -P "$PORT" -u "$USER" "-p$PASSWORD" "$DATABASE" "$@"; }

gunzip -c fixture.sql.gz | sql

# The offset is worked out before anything is written, or the update would be
# reading the column it is changing.
sql <<'EOSQL'
set @shift = datediff(
    date_sub(curdate(), interval 1 day),
    (select max(start_date) from rides)
);
update rides set
    start_date = date_add(start_date, interval @shift day),
    local_start_date = date_add(local_start_date, interval @shift day);
EOSQL

read -r first last teams main <<<"$(sql -N -B -e "
    select min(competition_date), max(competition_date),
           (select group_concat(id) from teams),
           (select min(id) from teams)
    from rides")"

# Wide enough that the competition is open whenever this runs, and the fixture
# sits inside it.
START_DATE="$(date -u -d "$first -1 day" +%Y-%m-%dT00:00:00+00:00 2>/dev/null ||
              date -u -j -f %Y-%m-%d -v-1d "$first" +%Y-%m-%dT00:00:00+00:00)"
END_DATE="$(date -u -d "+30 days" +%Y-%m-%dT23:59:59+00:00 2>/dev/null ||
            date -u -v+30d +%Y-%m-%dT23:59:59+00:00)"

echo "rides $first .. $last"
for line in "START_DATE=$START_DATE" "END_DATE=$END_DATE" \
            "TEAMS=$teams" "MAIN_TEAM=$main"; do
    echo "$line"
    [ -n "${GITHUB_ENV:-}" ] && echo "$line" >> "$GITHUB_ENV"
done
