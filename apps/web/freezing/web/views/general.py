"""
Created on Feb 10, 2013.

@author: hans
"""

import time
from datetime import datetime, timedelta
from re import findall, fullmatch, sub

from flask import (
    Blueprint,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask.typing import ResponseReturnValue
from sqlalchemy import text
from stravalib import Client
from stravalib.exc import Fault

from freezing.common import teams
from freezing.common.seasons import (
    JUNE_SOLSTICE,
    SEPTEMBER_EQUINOX,
    last_full_day_of_winter,
    season,
)
from freezing.model import meta
from freezing.model.orm import Athlete, Ride, RidePhoto, Team
from freezing.web import app, config, data
from freezing.web.autolog import log
from freezing.web.exc import MultipleTeamsError, NoTeamsError
from freezing.web.utils import auth
from freezing.web.utils.tribes import load_tribes, query_tribes
from freezing.web.utils.zipmap import registered_points
from freezing.web.views.shared_sql import team_leaderboard_query

blueprint = Blueprint("general", __name__)


class AccessDenied(RuntimeError):
    pass


# When a hashtag has a "/pointless/*" route instead of "/pointless/hashtag/*".
# Some of the generic leaderboards ought to be pure hashtag leaderboards.
custom_tag_pages = {
    "alaska": "generic/alaska",
    "civilwarmarker": "civilwarhistory",
    "civilwarstreet": "civilwarhistory",
    "commute": "generic/commute",
    "decasleaze": "generic/decasleaze",
    "foodrescue": "generic/foodrescue",
    "fsrealsuppleride": "generic/suppleride",
    "kidical": "generic/kidmiles",
    "rosshillloop": "generic/rosshillloop",
    "withkid": "generic/pointlesskids",
    "poggio": "segment/650024",
    "salmon": "segment/37893544",
}


def tag_page(tag):
    return next(
        (page for prefix, page in custom_tag_pages.items() if tag.startswith(prefix)),
        f"hashtag/{tag}",
    )


@app.template_filter("groupnum")
def groupnum(number):
    s = "%d" % number
    groups = []
    while s and s[-1].isdigit():
        groups.append(s[-3:])
        s = s[:-3]
    return s + ",".join(reversed(groups))


@app.template_filter("ess")
def ess(number):
    return "" if groupnum(number) == "1" else "s"


@app.template_filter("ord")
def ordinal(number):
    if number % 10 == 0 or number % 10 > 3 or number // 10 == 1:
        return "th"
    if number % 10 == 1:
        return "st"
    if number % 10 == 2:
        return "nd"
    return "rd"  # number % 10 == 3


@app.template_filter("myself")
def myself(number):
    # generic board formats the PK into a fancy string so unformat it
    athlete_id = int(sub(",", "", number)) if isinstance(number, str) else number
    return "myself" if session.get("athlete_id") == athlete_id else ""


@blueprint.route("/")
def index():
    q = text("""select count(*) as num_contestants from lbd_athletes""")

    indiv_count_res = meta.scoped_session().execute(q).one()
    contestant_count = indiv_count_res._mapping["num_contestants"]

    q = text("""
             select
               coalesce(sum(not coalesce(friend, false)), 0) as contestants,
               coalesce(sum(coalesce(friend, false)), 0) as friends
             from athletes
             where registered
             """)
    registered = meta.scoped_session().execute(q).one()._mapping

    q = text("""
            select count(*) as num_rides, coalesce(sum(R.moving_time),0) as moving_time,
                coalesce(sum(R.distance),0) as distance
            from rides R
            ;
        """)

    all_res = meta.scoped_session().execute(q).one()
    total_miles = int(all_res._mapping["distance"])
    total_hours = int(all_res._mapping["moving_time"]) / 3600
    total_rides = all_res._mapping["num_rides"]

    q = text("""
            select count(*) as num_rides, coalesce(sum(R.moving_time),0) as moving_time
            from rides R
            join ride_weather W on W.ride_id = R.id
            where W.ride_temp_avg < 32
            ;
        """)

    sub32_res = meta.scoped_session().execute(q).one()
    sub_freezing_hours = int(sub32_res._mapping["moving_time"]) / 3600

    q = text("""
            select count(*) as num_rides, coalesce(sum(R.moving_time),0) as moving_time
            from rides R
            join ride_weather W on W.ride_id = R.id
            where W.ride_rain = 1
            ;
        """)

    rain_res = meta.scoped_session().execute(q).one()
    rain_hours = int(rain_res._mapping["moving_time"]) / 3600

    q = text("""
            select count(*) as num_rides, coalesce(sum(R.moving_time),0) as moving_time
            from rides R
            join ride_weather W on W.ride_id = R.id
            where W.ride_snow = 1
            ;
        """)

    snow_res = meta.scoped_session().execute(q).one()
    snow_hours = int(snow_res._mapping["moving_time"]) / 3600

    # Grab some recent photos
    photos = (
        meta.scoped_session()
        .query(RidePhoto)
        .filter_by(primary=True)
        .join(Ride)
        .order_by(Ride.start_date.desc())
        .limit(12)
    )

    now_tz = datetime.now(config.TIMEZONE)
    after_competition_start = now_tz >= config.START_DATE
    before_competition_end = now_tz <= config.END_DATE
    delta_after_end = now_tz - config.END_DATE
    post_summer_solstice = now_tz >= season(now_tz.year, JUNE_SOLSTICE).astimezone(
        config.TIMEZONE
    )
    post_autumnal_equinox = now_tz >= season(now_tz.year, SEPTEMBER_EQUINOX).astimezone(
        config.TIMEZONE
    )

    tags = _trending_tags()

    today = min(now_tz, config.END_DATE)
    q = text("""
            select
                count(distinct athlete_id) as riders,
                coalesce(sum(R.moving_time),0) as moving_time,
                coalesce(sum(R.distance),0) as distance
            from rides R
            where R.competition_date >= '{}'
            ;
        """.format(today.date()))
    today_res = meta.scoped_session().execute(q).one()
    today_riders = int(today_res._mapping["riders"])
    today_hours = round(today_res._mapping["moving_time"]) / 3600
    today_miles = int(today_res._mapping["distance"])

    q = text("""
            select
                RE.personal_record as pr,
                count(RE.personal_record) as count
            from ride_efforts RE
            where RE.personal_record is not null
            group by personal_record
            ;
        """)
    pr_res = meta.scoped_session().execute(q).fetchall()
    prs = {res._mapping["pr"]: res._mapping["count"] for res in pr_res}
    # Don't try to do local legends. the strava api basically just tells us
    # which segments are are the legend for, at the time we call the api. so
    # we don't know when you became legend, and when we re-sync old rides
    # we will change the legendary status to what it is now rather than then.

    # Get teams sorted by points
    q = team_leaderboard_query()
    team_rows = meta.scoped_session().execute(q).fetchall()

    athlete_id = session.get("athlete_id")
    yourself = _rider_stats(athlete_id) if athlete_id else _non_rider_stats()
    athlete = meta.scoped_session().get(Athlete, athlete_id) if athlete_id else None

    registration_open = (
        config.REGISTRATION_DATE is not None
        and config.REGISTRATION_DATE <= now_tz < config.START_DATE
    )

    return render_template(
        "index.html",
        show_registration=registration_open,
        registered=bool(athlete and athlete.registered),
        registered_as=_registered_as(athlete),
        year=config.START_DATE.year,
        spring_is_over=post_summer_solstice,
        winter_is_coming=post_autumnal_equinox,
        next_winter_ends=last_full_day_of_winter(now_tz.year + 1, config.TIMEZONE),
        team_count=len(config.COMPETITION_TEAMS),
        contestant_count=contestant_count,
        registered_count=int(registered["contestants"]),
        zip_points=[] if after_competition_start else registered_points(),
        friend_count=int(registered["friends"]),
        total_rides=total_rides,
        total_hours=total_hours,
        total_miles=total_miles,
        rain_hours=rain_hours,
        snow_hours=snow_hours,
        sub_freezing_hours=sub_freezing_hours,
        today_riders=today_riders,
        today_hours=today_hours,
        today_miles=today_miles,
        bafs_is_live=after_competition_start,
        bafs_is_over=not before_competition_end,
        bafs_days_over=delta_after_end.days,
        pr_gold=prs.get(1, 0),
        pr_silver=prs.get(2, 0),
        pr_bronze=prs.get(3, 0),
        photos=list(photos),
        tags=tags,
        winners=team_rows[:3],  # + team_rows[4:][-1:]  # for last place too
        yourself=yourself,
    )


# The days of tagging the homepage's tag cloud is built from. A season tags
# about five thousand rides over eighty days, so a week is roughly the five
# hundred the old fixed count gave, and it moves with the competition.
_TRENDING_DAYS = 7


# Find the top 16 trending tags of the last few days, from ride titles and photo
# descriptions alike; the cloud does not care which kind of tag a board wants.
def _trending_tags():
    # Anchored on the competition rather than on the newest row, so one ride
    # with a bad clock cannot empty the window, and so the cloud still shows
    # the closing week once the season is over.
    until = min(datetime.now(config.TIMEZONE), config.END_DATE).date()
    since = until - timedelta(days=_TRENDING_DAYS)
    q = text("""
                select R.name as tagged
                from rides R
                where R.name like '%#%'
                  and R.competition_date between :since and :until
                union all
                select P.caption as tagged
                from ride_photos P join rides R on R.id = P.ride_id
                where P.caption like '%#%'
                  and R.competition_date between :since and :until
                ;
            """).bindparams(since=since, until=until)
    tag_count = {}
    original_tag = {}
    for res in meta.scoped_session().execute(q).fetchall():
        ride_tags = {}  # Prevent double-tagging
        for hashtag in findall(r"(?<=#)\w+", res._mapping["tagged"]):
            desuffix = fullmatch(
                r"(?i)(withkid|foodrescue|fsrealsuppleride).*", hashtag
            )
            hashtag = desuffix[1] if desuffix else hashtag
            if not fullmatch(
                r"(?i)(BAFS|FS|FreezingSaddles)?\d*", hashtag
            ):  # Ditch useless tags
                original_tag[hashtag.lower()] = hashtag
                ride_tags[hashtag.lower()] = 1
        for tag in ride_tags:
            tag_count[tag] = tag_count.get(tag, 0) + 1
    trending_tags = sorted(tag_count.items(), key=lambda t: t[1], reverse=True)
    top_tags = trending_tags[:16]
    if top_tags:
        min_count = top_tags[-1][1]
        scale = max(1, top_tags[0][1] - min_count)
        alpha_tags = sorted(top_tags, key=lambda t: t[0])
        return (
            [original_tag[t[0]], 1 + (t[1] - min_count) / scale, tag_page(t[0])]
            for t in alpha_tags
        )
    return []


# Get non-rider stats
def _non_rider_stats():
    start = config.START_DATE.date()
    now_tz = datetime.now(config.TIMEZONE)
    today = min(now_tz, config.END_DATE).date()
    total_days = 1 + (today - start).days
    after_competition_start = now_tz >= config.START_DATE
    before_competition_end = now_tz <= config.END_DATE

    # we could look to see if #competitors < #teams * max(#members)
    no_team = total_days <= 31 and config.COMPETITION_TEAMS

    return {
        "no_team": no_team,
        "not_logged_in": after_competition_start and before_competition_end,
    }


def _registered_as(athlete: Athlete | None) -> str | None:
    """How a registered athlete is taking part, as the front page words it."""
    if not (athlete and athlete.registered):
        return None
    if athlete.friend:
        return "friend"
    if athlete.registration and athlete.registration.team_captain:
        return "potential captain"
    return "competitor"


# Get rider stats
def _rider_stats(athlete_id):
    rank = meta.scoped_session().execute(text("""
                with scores as (
                  select A.id, sum(DS.points) as score
                  from daily_scores DS join lbd_athletes A on A.id = DS.athlete_id
                  group by A.id
                ), ranked_scores as (
                  select id, rank() over (order by score desc) as place from scores
                )
                select place from ranked_scores where id = :athlete_id
                """).bindparams(athlete_id=athlete_id)).fetchone()
    team_rank = meta.scoped_session().execute(text("""
                with scores as (
                  select T.id, sum(DS.points) as score
                  from daily_scores DS join teams T on T.id = DS.team_id where not T.leaderboard_exclude
                  group by T.id
                ), ranked_scores as (
                  select id, rank() over (order by score desc) as place from scores
                )
                select RS.place from ranked_scores RS join lbd_athletes A on RS.id = A.team_id where A.id = :athlete_id
                """).bindparams(athlete_id=athlete_id)).fetchone()
    ride_stats = meta.scoped_session().execute(text("""
                select
                  count(id) as rides,
                  coalesce(sum(moving_time), 0) as time,
                  coalesce(sum(distance), 0) as distance
                from rides R
                where R.athlete_id = :athlete_id
                """).bindparams(athlete_id=athlete_id)).one()
    ride_days = {res[0] for res in (meta.scoped_session().execute(text("""
                    select ride_date from daily_scores DS where DS.athlete_id = :athlete_id
                    """).bindparams(athlete_id=athlete_id)).fetchall())}
    athlete = meta.scoped_session().get(Athlete, athlete_id)
    # Null for an athlete in none of the season's clubs, or in two real teams.
    team = athlete.team
    on_team = team is not None and not team.leaderboard_exclude
    start = config.START_DATE.date()
    now_tz = datetime.now(config.TIMEZONE)
    today = min(now_tz, config.END_DATE).date()
    yesterday = today - timedelta(days=1)
    total_days = 1 + (today - start).days
    streak = next(
        (
            r
            for r in range(total_days)
            if (yesterday - timedelta(days=r)) not in ride_days
        ),
        0,
    ) + (1 if today in ride_days else 0)
    game_on = datetime.now().date() <= today
    # if within the first month you are not on a team then explain
    no_team = total_days <= 31 and not on_team and config.COMPETITION_TEAMS

    return {
        "rank": rank[0] if rank else None,
        "team_rank": team_rank[0] if team_rank else None,
        "rides": int(ride_stats[0]),
        "hours": round(ride_stats[1] / 3600),
        "miles": int(ride_stats[2]),
        "days": len(ride_days),
        "total_days": total_days,
        "missed_today": game_on and today not in ride_days,
        "missed_yesterday": yesterday >= start and yesterday not in ride_days,
        "hour": datetime.now(config.START_DATE.tzinfo).hour,
        "streak": streak,
        "every_day": total_days > 0 and streak == total_days,
        "team_name": team.name if on_team else None,
        "no_team": no_team,
        "unauthorized": athlete.refresh_token is None,
    }


@blueprint.route("/discord")
def discord():
    return render_template("discord.html") if session.get("athlete_id") else join()


@blueprint.route("/logout")
def logout():
    session.clear()
    return redirect(url_for(".index"))


@blueprint.route("/authorize")
@blueprint.route("/login")
def join():
    # Forced, Strava asks again which account and what it may read.
    approval_prompt = "force" if "reconnect" in request.args else "auto"
    c = Client()
    public_url = c.authorization_url(
        client_id=config.STRAVA_CLIENT_ID,
        redirect_uri=url_for(".authorization", _external=True),
        approval_prompt=approval_prompt,
        scope=["read", "activity:read", "profile:read_all"],
    )
    private_url = c.authorization_url(
        client_id=config.STRAVA_CLIENT_ID,
        redirect_uri=url_for(".authorization", _external=True),
        approval_prompt=approval_prompt,
        scope=["read_all", "activity:read_all", "profile:read_all"],
    )
    now_tz = datetime.now(config.START_DATE.tzinfo)
    return render_template(
        "authorize.html",
        public_authorize_url=public_url,
        private_authorize_url=private_url,
        after_competition_start=now_tz >= config.START_DATE,
    )


def _refresh_team(athlete: Athlete) -> Team | None:
    """
    Ask Strava for the athlete's clubs rather than wait for its notice of joining.

    The notice is sometimes lost. Leaves things as they were if Strava can't
    say, and asks at most every few seconds, since the page refreshes itself
    whenever its tab is shown.
    """
    if config.ENVIRONMENT == "localdev":
        return None
    now = time.time()
    if now - session.get("club_checked", 0) < 10:
        return None
    session["club_checked"] = now
    try:
        strava_athlete = data.fetch_strava_athlete(athlete)
    except Exception:
        log.exception(f"Could not read athlete {athlete.id}'s clubs from Strava")
        return None
    _note_blank(strava_athlete)
    try:
        return data.register_athlete_team(strava_athlete, athlete)
    except (MultipleTeamsError, NoTeamsError) as e:
        log.info(f"Athlete {athlete.id} has no team yet: {e}")
    return None


def _note_blank(strava_athlete) -> bool:
    """Remember for the registration pages whether the Strava account looks blank."""
    blank = teams.looks_blank(strava_athlete)
    if blank:
        log.info(f"Strava athlete {strava_athlete.id} looks blank")
        session["blank_strava"] = strava_athlete.id
    else:
        session.pop("blank_strava", None)
    return blank


@blueprint.route("/register")
def register():
    step = request.args.get("step", "intro")
    # Strava only shows its permissions again when forced to; otherwise a rider
    # reconnecting keeps the ones they chose before.
    reconnect = request.args.get("profile") in ("missing", "blank", "account")
    approval_prompt = "force" if reconnect else "auto"
    c = Client()
    public_url = c.authorization_url(
        client_id=config.STRAVA_CLIENT_ID,
        redirect_uri=url_for(".authorization", _external=True),
        approval_prompt=approval_prompt,
        scope=["read", "activity:read", "profile:read_all"],
        state="register",
    )
    private_url = c.authorization_url(
        client_id=config.STRAVA_CLIENT_ID,
        redirect_uri=url_for(".authorization", _external=True),
        approval_prompt=approval_prompt,
        scope=["read_all", "activity:read_all", "profile:read_all"],
        state="register",
    )
    if config.ENVIRONMENT == "localdev":
        private_url = public_url = url_for(".authorization", state="register")

    athlete_id = session.get("athlete_id")
    athlete = (
        meta.scoped_session().query(Athlete).filter_by(id=athlete_id).first()
        if athlete_id
        else None
    )
    team = (
        meta.scoped_session()
        .query(Team)
        .join(Athlete)
        .filter(Athlete.id == athlete_id)
        .first()
        if athlete_id
        else None
    )

    # Registering is for riders whose rides we can read, so an athlete whose
    # tokens were forgotten goes back to connecting Strava.
    authorized = athlete is not None and athlete.refresh_token is not None
    if athlete and not authorized and step not in ("intro", "login"):
        return redirect(url_for(".register", step="login"))

    if step == "club" and "refresh" in request.args and athlete and not team:
        team = _refresh_team(athlete)

    # Both forms live on the Wordpress site, which redirects back to this step;
    # the friends' form adds friend=true. The Next button for riders already
    # registered comes here without it, so only a new registration says
    # they're not a friend.
    friend = request.args.get("friend") == "true"
    if step == "complete" and athlete and not athlete.registered:
        log.info(
            f"Athlete {athlete.id} ({athlete.name}) completed registration"
            f"{' as a friend' if friend else ''}"
        )
        athlete.registered = True
        athlete.friend = friend
    elif step == "complete" and athlete and friend:
        athlete.friend = True

    now_tz = datetime.now(config.START_DATE.tzinfo)
    return render_template(
        "register.html",
        step=step,
        athlete=athlete,
        authorized=authorized,
        team=team,
        blank_strava=athlete is not None and session.get("blank_strava") == athlete.id,
        tribal_groups=load_tribes() if step == "tribes" else [],
        tribes=query_tribes(athlete.id) if step == "tribes" and athlete else {},
        mean_team=config.MAIN_TEAM,
        public_authorize_url=public_url,
        private_authorize_url=private_url,
        after_competition_start=now_tz >= config.START_DATE,
        registration_open=g.registration_open,
    )


@blueprint.route("/authorization")
def authorization() -> ResponseReturnValue:
    """
    Handle the redirect from Strava that includes parameters.

    - state
    - code
    - error

    For local development (ENVIRONMENT=localdev), we can bypass the Strava authorization
    by passing the athlete ID as a query parameter. This is useful for testing the site without
    having to authenticate with Strava each time.

    http://localhost:5000/authorization?athlete_id=123456
    """
    error = request.args.get("error")
    if error:
        return render_template(
            "authorization_error.html",
            error=error,
        )
    multiple_teams = None
    no_teams = False
    team = None
    message = None
    state = None
    profile_missing = False
    blank = False
    log.info(f"Authorization request host: {request.host}")
    if config.ENVIRONMENT == "localdev" and request.host.split(":")[0] in [
        "localhost",
        "127.0.0.1",
    ]:
        # if config.ENVIRONMENT == "localdev":
        # Cheat and pretend we're authorized
        athlete_id = request.args.get("athlete_id", session.get("athlete_id"))
        athlete = (
            meta.scoped_session()
            .query(Athlete)
            .filter(Athlete.id == int(athlete_id))
            .first()
            if athlete_id is not None
            else meta.scoped_session().query(Athlete).first()
        )
        athlete_id = athlete.id if athlete else 0
        log.warning(
            f"Local development login bypass exercised for athlete {athlete_id}"
        )

        class MockAthlete:
            firstname: str = "Ferd"
            lastname: str = "Berferd"
            profile_medium: str = "/img/logo-blue-sm.png"
            email: str = "ferd.berferd@example.com"

            def __init__(self, athlete_id: int, firstname: str, lastname: str):
                self.id = athlete_id
                self.firstname = firstname
                self.lastname = lastname

        parts = (
            athlete.display_name.split(" ") if athlete and athlete.display_name else []
        )
        strava_athlete = MockAthlete(
            athlete_id,
            parts[0] if parts else "Dev",
            parts[-1] if len(parts) > 1 else "User",
        )
        message = "Local development enabled"
        state = request.args.get("state")
    else:
        code = request.args.get("code")
        scope = request.args.get("scope")
        state = request.args.get("state")
        log.info(f"Authorization scope: {scope}, state: {state}")
        profile_missing = "profile:read_all" not in (scope or "").split(",")

        # Strava sends people here with a code. Anyone arriving without one has
        # opened the address by hand or followed a stale link, and has not
        # failed at anything: start them off again rather than showing them an
        # error about a code they never had.
        if not code:
            return redirect(url_for(".join"))

        client = Client()
        try:
            token_dict = client.exchange_code_for_token(
                client_id=config.STRAVA_CLIENT_ID,
                client_secret=config.STRAVA_CLIENT_SECRET,
                code=code,
            )
        except Fault as fault:
            # A code is good for one exchange, so a refresh or a back button
            # arrives with one Strava has already spent.
            log.info(f"Strava would not take the authorization code: {fault}")
            return render_template(
                "authorization_error.html", error="the code had already been used"
            )
        # Use the now-authenticated client to get the current athlete
        strava_athlete = teams.fill_clubs(client, client.get_athlete())
        log.info(
            f"Strava athlete {strava_athlete.id} ({strava_athlete.firstname} "
            f"{strava_athlete.lastname}), {len(strava_athlete.clubs or [])} clubs"
        )
        blank = _note_blank(strava_athlete)
        athlete = data.register_athlete(strava_athlete, token_dict)
        log.info(f"Received athlete auth [id: {athlete.id}, name: {athlete.name}]")
        try:
            team = data.register_athlete_team(
                strava_athlete=strava_athlete,
                athlete_model=athlete,
            )
        except MultipleTeamsError as multx:
            multiple_teams = multx.teams
            message = multx
        except NoTeamsError as noteamx:
            no_teams = True
            message = noteamx

    # We autocommit at teardown_request, but we really want to commit
    # before rendering success in case transaction commit fails.
    meta.scoped_session().commit()
    auth.login_athlete(strava_athlete)

    # Thanks https://stackoverflow.com/a/32926295/424301 for the hint on tzinfo aware compares
    after_competition_start = datetime.now(config.TIMEZONE) > config.START_DATE
    if message:
        log.info(f"Authorization message: {message}")

    if state == "register":
        # Without it, Strava hides the clubs of anyone whose profile isn't
        # public, so we can't find their team.
        if profile_missing:
            return redirect(url_for(".register", step="login", profile="missing"))
        if blank:
            return redirect(url_for(".register", step="login", profile="blank"))
        return redirect(url_for(".register", step="club"))

    return render_template(
        "authorization_success.html",
        after_competition_start_start=after_competition_start,
        athlete=strava_athlete,
        competition_teams_assigned=len(config.COMPETITION_TEAMS) > 0,
        team=team,
        message=message,
        main_team_page=f"https://strava.com/clubs/{config.MAIN_TEAM}",
        multiple_teams=multiple_teams,
        no_teams=no_teams,
        blank=blank,
        not_registered=athlete is not None and not athlete.registered,
        rides_url=url_for("user.rides"),
    )
