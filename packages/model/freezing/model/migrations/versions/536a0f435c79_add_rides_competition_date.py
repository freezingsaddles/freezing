from alembic import op

from freezing.model.config import config

"""add rides competition_date

Revision ID: 536a0f435c79
Revises: e4814ed4c8aa
Create Date: 2026-09-19 14:02:51.338217

Which day of the competition a ride counts towards, worked out by the database
from start_date so that it cannot drift and nothing has to remember to write it.
Adding it computes the value for every existing row.

The expression names the competition's zone, so a change of TIMEZONE is an alter
rather than something that silently stops being true.

"""

# revision identifiers, used by Alembic.
revision = "536a0f435c79"
down_revision = "e4814ed4c8aa"


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
      {} as ride_date
    from
      rides R join athletes A on A.id = R.athlete_id
    group by
      A.id,
      A.team_id,
      ride_date
"""


def _rebuild_daily_scores(ride_date: str):
    # freezing.model only creates the views for a database with no tables, so
    # this is the only place an existing one is brought up to date.
    op.execute("drop view if exists daily_scores")
    op.execute(_DAILY_SCORES.format(ride_date))


def upgrade():
    op.execute(
        "alter table rides add column competition_date date "
        "generated always as (date(CONVERT_TZ(start_date, 'UTC', '{}'))) stored".format(
            config.TIMEZONE
        )
    )
    op.create_index("ix_rides_competition_date", "rides", ["competition_date"])
    _rebuild_daily_scores("R.competition_date")


def downgrade():
    _rebuild_daily_scores(
        "date(CONVERT_TZ(R.start_date, 'UTC', '{}'))".format(config.TIMEZONE)
    )
    op.drop_index("ix_rides_competition_date", table_name="rides")
    op.drop_column("rides", "competition_date")
