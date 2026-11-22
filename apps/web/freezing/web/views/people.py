from datetime import datetime, timedelta
from math import ceil

from flask import Blueprint, abort, render_template, session
from sqlalchemy import case, distinct, func, text

from freezing.model import meta
from freezing.model.orm import Athlete, AthleteSeason, Team
from freezing.web import config
from freezing.web.utils.auth import requires_auth
from freezing.web.utils.tribes import load_tribes, query_tribes

blueprint = Blueprint("people", __name__)


def get_local_datetime() -> datetime:
    return datetime.now(config.TIMEZONE)


def get_today() -> datetime:
    """Sometimes you have an old database for testing and you need to set today to be something that is not actually today."""
    if False:
        return datetime(2024, 3, 18, tzinfo=config.TIMEZONE)
    return get_local_datetime()


@blueprint.route("/")
def people_list_users():
    q = text("""
             select A.id, A.display_name, A.team_id, T.name as team_name,
             A.registered, A.friend,
             count(R.id) as rides, coalesce(sum(R.distance), 0) as miles
             from athletes A
             join teams T on T.id = A.team_id and not T.leaderboard_exclude
             left join rides R on R.athlete_id = A.id
             group by A.id, A.display_name, A.team_id, T.name, A.registered, A.friend
             order by lower(A.display_name)
             """)
    return render_template(
        "people/list.html", users=meta.scoped_session().execute(q).fetchall()
    )


@blueprint.route("/me")
@requires_auth
def people_show_me():
    return people_show_person(session["athlete_id"])


@blueprint.route("/<user_id>")
def people_show_person(user_id):
    our_user = meta.scoped_session().query(Athlete).filter_by(id=user_id).first()
    if not our_user:
        abort(404)
    if our_user.profile_photo and not str.startswith(our_user.profile_photo, "http"):
        our_user.profile_photo = None

    our_team = meta.scoped_session().query(Team).filter_by(id=our_user.team_id).first()
    stats = meta.scoped_session().execute(text("""
                with scores as (
                  select athlete_id, sum(points) as points, count(*) as days
                  from daily_scores group by athlete_id
                ), ranked as (
                  select S.athlete_id, rank() over (order by S.points desc) as place
                  from scores S join lbd_athletes A on A.id = S.athlete_id
                )
                select
                  (select place from ranked where athlete_id = :id) as place,
                  (select count(*) from ranked) as ranked,
                  (select points from scores where athlete_id = :id) as points,
                  (select days from scores where athlete_id = :id) as days,
                  count(R.id) as rides,
                  coalesce(sum(R.distance), 0) as miles,
                  coalesce(sum(R.moving_time), 0) as seconds
                from rides R where R.athlete_id = :id
                """).bindparams(id=user_id)).one()._mapping

    q = text("""
           with daily_rides as (
            select R.competition_date as ride_date,
            R.distance as distance,
            W.ride_temp_avg as ride_temp
            from rides R left outer join ride_weather W on W.ride_id = R.id
            where R.athlete_id = :athlete_id
          )
          select ride_date, sum(distance) as distance, avg(ride_temp) as ride_temp
            from daily_rides
            group by ride_date
            having distance >= 1
            order by ride_date;
            """).bindparams(athlete_id=user_id)

    indiv_q = meta.scoped_session().execute(q).fetchall()
    start = config.START_DATE - timedelta(days=(config.START_DATE.weekday() + 1) % 7)
    weeks = ceil((config.END_DATE - start).days / 7)

    def color(res) -> str:
        distance = res._mapping["distance"]
        temp = res._mapping["ride_temp"]
        hue = int(min(360, max(240, 300 + (temp - 44) * 6))) if temp else 300
        sat = 100  # max(1, min(100, int(distance * 10)))
        lig = int(50 + min(25, max(0, (distance - 10))))
        alp = int(min(100, max(0, (distance * 500) ** 0.5)))
        return f"hsla({hue}, {sat}%, {lig}%, {alp}%)"

    mosaic = {
        (res._mapping["ride_date"] - start.date()).days: color(res) for res in indiv_q
    }

    other_teams = sorted(
        (t for t in our_user.clubs if t.id != our_user.team_id), key=lambda t: t.name
    )

    tribal_groups = load_tribes()
    my_tribes = query_tribes(user_id)

    return render_template(
        "people/show.html",
        seasons=past_seasons(our_user.id),
        data={
            "environment": config.ENVIRONMENT,
            "my_tribes": my_tribes,
            "other_teams": other_teams,
            "observer_teams": config.OBSERVER_TEAMS,
            "team": our_team,
            "stats": stats,
            "season_days": max(
                0,
                (
                    min(get_today(), config.END_DATE).date() - config.START_DATE.date()
                ).days
                + 1,
            ),
            "tribal_groups": tribal_groups,
            "user": our_user,
            "mosaic": mosaic,
            "weeks": weeks,
            "first_day": (config.START_DATE - start).days,
            "last_day": (config.END_DATE - start).days,
        },
    )


def past_seasons(athlete_id: int) -> list[dict]:
    """Return the archived seasons, latest first, with the size of each field."""
    session = meta.scoped_session()
    seasons = (
        session.query(AthleteSeason)
        .filter_by(athlete_id=athlete_id)
        .order_by(AthleteSeason.year.desc())
        .all()
    )
    if not seasons:
        return []
    fields = {
        year: (athletes, teams)
        for year, athletes, teams in session.query(
            AthleteSeason.year,
            func.count(AthleteSeason.rank),
            func.count(
                distinct(
                    case((AthleteSeason.team_rank.isnot(None), AthleteSeason.team_id))
                )
            ),
        )
        .filter(AthleteSeason.year.in_([s.year for s in seasons]))
        .group_by(AthleteSeason.year)
    }
    return [
        {
            "season": s,
            "athletes": fields[s.year][0],
            "teams": fields[s.year][1],
        }
        for s in seasons
    ]


def competition_done(loc_time):
    end_time = config.END_DATE
    return loc_time > end_time


@blueprint.route("/ridedays")
def ridedays():
    q = text("""
                SELECT
                    a.id,
                    a.display_name,
                    count(b.ride_date) as rides,
                    sum(b.distance) as miles,
                    sum(case when b.ride_date = :today then 1 else 0 end) as today
                FROM
                    lbd_athletes a,
                    daily_scores b where a.id = b.athlete_id
                group by b.athlete_id
                order by
                    case when rides = :total then 0 when rides = :total - 1 and today = 0 then 1 else 2 end,
                    rides desc,
                    display_name
                ;
                """)
    loc_time = get_today()
    loc_total_days = (
        min(loc_time.toordinal(), config.END_DATE.toordinal())
        - config.START_DATE.toordinal()
        + 1
    )
    all_done = competition_done(loc_time)

    def contender(rides: int, today: int) -> bool:
        return rides == loc_total_days - 1 and today == 0 and not all_done

    ride_days = [
        (
            x._mapping["id"],
            x._mapping["display_name"],
            x._mapping["rides"],
            x._mapping["miles"],
            contender(x._mapping["rides"], x._mapping["today"]),
        )
        for x in meta.scoped_session()
        .execute(q.bindparams(today=loc_time.date(), total=loc_total_days))
        .fetchall()
    ]
    return render_template(
        "people/ridedays.html",
        ride_days=ride_days,
        num_days=loc_total_days,
        all_done=all_done,
        every_day_riders=sum(x[2] == loc_total_days for x in ride_days),
        contenders=sum(x[4] for x in ride_days),
        remainders=sum(x[2] < loc_total_days and not x[4] for x in ride_days),
    )


@blueprint.route("/friends")
def friends():
    q = text("""
             select A.id, A.team_id, A.display_name as athlete_name, T.name as team_name,
             sum(DS.distance) as total_distance, sum(DS.points) as total_score,
             count(DS.points) as days_ridden
             from daily_scores DS
             join athletes A on A.id = DS.athlete_id
             join teams T on T.id = A.team_id
             where T.leaderboard_exclude
             group by A.id, A.display_name
             order by lower(A.display_name) asc
             ;
             """)

    indiv_rows = meta.scoped_session().execute(q).fetchall()

    return render_template(
        "people/friends.html",
        indiv_rows=indiv_rows,
    )
