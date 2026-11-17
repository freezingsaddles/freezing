#!/usr/bin/env bash
# archive-backup.sh
#
# Restores a season's mysqldump into a throwaway MySQL container and writes the
# SQL that files its results in athlete_seasons, for loading into production.
#
# Usage:
#   packages/model/bin/archive-backup.sh freezing-2024-11-24.sql.xz > season-2024.sql
#
# Needs docker and the workspace installed (uv sync --all-packages). The dump
# may be plain, .gz or .xz. The container is removed afterwards unless KEEP=1.
#
# What the dumps need before they load into a fresh server:
#   * Only the rows of rides, athletes and teams are loaded, which is all the
#     archiver reads. The 2020 dump's ride_geo, from MySQL 5.6, holds geometry
#     that 8.x refuses, and the rest only take time.
#   * The views' DEFINER (freezing or fsadmin) does not exist there, and a view
#     whose definer is missing cannot be read. The clauses are stripped, so the
#     views belong to root.
#   * GTID_PURGED and SQL_LOG_BIN, in the 2023 and later dumps, are refused.
#   * The 2021 and 2022 dumps have mysqldump's own warnings and errors written
#     into them as lines starting "mysqldump:".
#   * The 2020-2022 dumps come from MySQL 5.6, so the server runs with an empty
#     sql_mode rather than 8.x's strict one.
#   * daily_scores dates rides with CONVERT_TZ, which needs the server's time
#     zone tables; the mysql image loads them, and the archiver refuses a
#     season with undated days.

set -euo pipefail

DUMP=${1:?Usage: $0 DUMP [freezing-archive-season args...]}
shift
MYSQL_IMAGE=${MYSQL_IMAGE:-mysql:8.4}
NAME=freezing-archive-$$
PASSWORD=scratch

case "$DUMP" in
*.xz) cat_dump() { xz -dc "$DUMP"; } ;;
*.gz) cat_dump() { gzip -dc "$DUMP"; } ;;
*) cat_dump() { cat "$DUMP"; } ;;
esac

cleanup() {
    if [[ "${KEEP:-}" != 1 ]]; then
        docker rm -f "$NAME" >/dev/null
    else
        echo "kept container $NAME on port $PORT" >&2
    fi
}

docker run -d --name "$NAME" -p 127.0.0.1::3306 \
    -e MYSQL_ROOT_PASSWORD=$PASSWORD -e MYSQL_DATABASE=freezing \
    "$MYSQL_IMAGE" --sql-mode= >/dev/null
trap cleanup EXIT
PORT=$(docker port "$NAME" 3306/tcp | head -1 | sed 's/.*://')

echo "waiting for $NAME" >&2
# The image's entrypoint runs a server without networking while it sets up, so
# wait for the root password to work over TCP.
until docker exec -e MYSQL_PWD=$PASSWORD "$NAME" mysql -uroot -h127.0.0.1 -e 'select 1' >/dev/null 2>&1; do
    sleep 2
done

echo "restoring $DUMP" >&2
# Perl rather than grep and sed: the dumps are not all valid UTF-8, and their
# extended inserts run to megabytes a line.
cat_dump |
    perl -ne '
        next if /^INSERT INTO `(?!(rides|athletes|teams)`)/;
        next if /GTID_PURGED|SQL_LOG_BIN|^mysqldump:/;
        s/DEFINER=`[^`]*`@`[^`]*`//;
        print;
    ' |
    docker exec -i -e MYSQL_PWD=$PASSWORD "$NAME" mysql -uroot freezing

uv run --no-sync --project "$(dirname "$0")/../../.." freezing-archive-season --sql \
    --source "mysql+pymysql://root:$PASSWORD@127.0.0.1:$PORT/freezing?charset=utf8mb4" "$@"
