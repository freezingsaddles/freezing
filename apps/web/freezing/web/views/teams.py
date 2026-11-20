from datetime import timedelta
from math import ceil

from flask import Blueprint, abort, render_template
from sqlalchemy import text

from freezing.model import meta
from freezing.model.orm import Team
from freezing.web import config
from freezing.web.views.shared_sql import team_riders

blueprint = Blueprint("teams", __name__)


@blueprint.route("/<team_id>")
def teams_show_team(team_id):
    our_team = meta.scoped_session().query(Team).filter_by(id=team_id).first()
    if not our_team:
        abort(404)

    if our_team.profile_photo and not str.startswith(our_team.profile_photo, "http"):
        our_team.profile_photo = None
    riders = team_riders(our_team.id)

    q = text(f"""
             select
               A.id as athlete_id,
               A.display_name as athlete_name,
               sum(DS.distance) as total_distance,
               sum(DS.points) as total_score,
               count(DS.points) as days_ridden
             from
               daily_scores DS
                 join athletes A on A.id = DS.athlete_id
             where A.id in ({riders})
             group by A.id, A.display_name
             order by display_name asc
             ;
             """).bindparams(team_id=our_team.id)

    members = meta.scoped_session().execute(q).fetchall()

    # Counted as the team leaderboard counts them.
    q = text(f"""
             select
               coalesce(sum(DS.points), 0) as points,
               count(DS.points) as days,
               coalesce(sum(DS.distance), 0) as distance
             from daily_scores DS
             where DS.athlete_id in ({riders})
             ;
             """).bindparams(team_id=our_team.id)
    totals = meta.scoped_session().execute(q).one()._mapping

    q = text(f"""
             select
               coalesce(sum(case when W.ride_temp_avg < 32 then R.moving_time end), 0)
                 as sub_freezing,
               coalesce(sum(case when W.ride_rain = 1 then R.moving_time end), 0)
                 as rain,
               coalesce(sum(case when W.ride_snow = 1 then R.moving_time end), 0)
                 as snow
             from rides R
               join ride_weather W on W.ride_id = R.id
             where R.athlete_id in ({riders})
             ;
             """).bindparams(team_id=our_team.id)
    weather = meta.scoped_session().execute(q).one()._mapping

    q = text(f"""
             select RE.personal_record as pr, count(*) as count
             from ride_efforts RE
               join rides R on R.id = RE.ride_id
             where R.athlete_id in ({riders}) and RE.personal_record is not null
             group by RE.personal_record
             ;
             """).bindparams(team_id=our_team.id)
    prs = {
        res._mapping["pr"]: res._mapping["count"]
        for res in meta.scoped_session().execute(q).fetchall()
    }

    stats = {
        "points": totals["points"],
        "days": totals["days"],
        "miles": totals["distance"],
        "sub_freezing_hours": int(weather["sub_freezing"]) / 3600,
        "rain_hours": int(weather["rain"]) / 3600,
        "snow_hours": int(weather["snow"]) / 3600,
        "pr_gold": prs.get(1, 0),
        "pr_silver": prs.get(2, 0),
        "pr_bronze": prs.get(3, 0),
    }

    q = text(f"""
           with daily_rides as (
            select R.competition_date as ride_date,
            R.athlete_id,
            sum(R.distance) as distance
            from rides R
            where R.athlete_id in ({riders})
            group by ride_date, athlete_id
          )
          select ride_date, count(athlete_id) as athletes
            from daily_rides
            where distance >= 1
            group by ride_date
            order by ride_date;
            """).bindparams(team_id=our_team.id)

    indiv_q = meta.scoped_session().execute(q).fetchall()
    start = config.START_DATE - timedelta(days=(config.START_DATE.weekday() + 1) % 7)
    weeks = ceil((config.END_DATE - start).days / 7)

    count = len(members)

    def color(res) -> str:
        athletes = res._mapping["athletes"]
        alp = int(min(100, max(0, athletes * 100 // count))) if count else 0
        lig = 45 if athletes < (count - 2) else 50 + 15 * (athletes - count + 2)
        return f"hsla(197, 97%, {lig}%, {alp}%)"

    mosaic = {
        (res._mapping["ride_date"] - start.date()).days: color(res) for res in indiv_q
    }

    return render_template(
        "teams/show.html",
        team=our_team,
        club=our_team.id in config.OBSERVER_TEAMS,
        members=list(members),
        stats=stats,
        mosaic=mosaic,
        weeks=weeks,
        first_day=(config.START_DATE - start).days,
        last_day=(config.END_DATE - start).days,
    )
