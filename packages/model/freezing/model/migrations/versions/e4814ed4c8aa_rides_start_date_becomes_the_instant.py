from alembic import op

from freezing.model.config import config

"""rides start_date becomes the instant

Revision ID: e4814ed4c8aa
Revises: c6ec6820043d
Create Date: 2026-09-19 09:41:17.224903

local_start_date already holds what start_date held, so start_date can become
naive UTC and stop needing the row's own timezone to mean anything. Ordering and
comparison then work on it directly, and only the competition-day questions
convert, from a zone that is the same for every row.

The views have to be rebuilt here rather than left to freezing.model, which
only creates them for a database that has no tables yet.

"""

# revision identifiers, used by Alembic.
revision = "e4814ed4c8aa"
down_revision = "c6ec6820043d"


_DAILY_SCORES = """
    create view daily_scores as
    select
      A.team_id,
      R.athlete_id,
      sum(R.distance) as distance,
      case
        when sum(R.distance) < 1 then 0
        when sum(R.distance) < 10 then
          10 + 0.5 * (21 * sum(R.distance) -
          (sum(R.distance) * sum(R.distance)))
        else 65 + sum(R.distance) - 10
      end as points,
      date(CONVERT_TZ(R.start_date, {}, '{}')) as ride_date
    from
      rides R join athletes A on A.id = R.athlete_id
    group by
      A.id,
      A.team_id,
      ride_date
"""

_BUILD_RIDE_DAYLIGHT = """
    create view _build_ride_daylight as
    select R.id as ride_id, date(R.{col}) as ride_date,
    sec_to_time(R.elapsed_time) as elapsed,
    sec_to_time(R.moving_time) as moving,
    TIME(R.{col}) as start_time,
    TIME(date_add(R.{col}, interval R.elapsed_time second)) as end_time,
    W.sunrise, W.sunset
    from rides R
    join ride_weather W on W.ride_id = R.id
"""

_RIDE_DAYLIGHT = """
    create view ride_daylight as
    select ride_id, ride_date, start_time, end_time, sunrise, sunset, moving,
    IF(start_time < sunrise, LEAST(TIMEDIFF(sunrise, start_time), moving), sec_to_time(0)) as before_sunrise,
    IF(end_time > sunset, LEAST(TIMEDIFF(end_time, sunset), moving), sec_to_time(0)) as after_sunset
    from _build_ride_daylight
"""


def _rebuild_views(scores_source: str, daylight_column: str):
    op.execute("drop view if exists ride_daylight")
    op.execute("drop view if exists _build_ride_daylight")
    op.execute("drop view if exists daily_scores")
    op.execute(_DAILY_SCORES.format(scores_source, config.TIMEZONE))
    op.execute(_BUILD_RIDE_DAYLIGHT.format(col=daylight_column))
    op.execute(_RIDE_DAYLIGHT)


def upgrade():
    # timezone is the rider's and local_start_date is their wall clock, so this
    # is exact. A row without a timezone cannot be converted and keeps what it
    # has, which is what every reader assumed of it anyway.
    op.execute(
        "update rides set start_date = CONVERT_TZ(local_start_date, timezone, 'UTC') "
        "where timezone is not null and local_start_date is not null"
    )
    _rebuild_views("'UTC'", "local_start_date")


def downgrade():
    op.execute(
        "update rides set start_date = CONVERT_TZ(start_date, 'UTC', timezone) "
        "where timezone is not null"
    )
    _rebuild_views("R.timezone", "start_date")
