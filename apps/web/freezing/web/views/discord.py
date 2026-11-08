"""Linking an athlete's Discord account, through Discord's OAuth2."""

from secrets import token_urlsafe
from urllib.parse import urlencode

import requests
from flask import (
    Blueprint,
    abort,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from freezing.model import meta
from freezing.model.orm import Athlete
from freezing.web import config
from freezing.web.autolog import log

blueprint = Blueprint("discord", __name__)

API = "https://discord.com/api/v10"


def _after(name):
    # Names, not urls: nothing the browser sends reaches redirect() as a url.
    after = {"register": url_for("general.register", step="discord")}
    return after.get(name, url_for("general.discord"))


def _redirect_uri():
    # Discord matches the uri exactly, and the proxy in front of gunicorn
    # does not tell it the request came in over https.
    scheme = "http" if config.ENVIRONMENT == "localdev" else "https"
    return url_for(".callback", _external=True, _scheme=scheme)


@blueprint.before_request
def require_linking():
    if not config.DISCORD_CLIENT_ID:
        abort(404)
    if not session.get("athlete_id"):
        return redirect(url_for("general.join"))


@blueprint.route("/link")
def link():
    state = token_urlsafe()
    session["discord_state"] = state
    session["discord_next"] = request.args.get("next")
    scope = "identify guilds.join" if config.DISCORD_BOT_TOKEN else "identify"
    query = urlencode(
        {
            "client_id": config.DISCORD_CLIENT_ID,
            "redirect_uri": _redirect_uri(),
            "response_type": "code",
            "scope": scope,
            "state": state,
        }
    )
    return redirect(f"https://discord.com/oauth2/authorize?{query}")


@blueprint.route("/callback")
def callback():
    state = session.pop("discord_state", None)
    after = _after(session.pop("discord_next", None))
    # Cancelling on Discord's screen comes back as error=access_denied.
    if request.args.get("error"):
        return redirect(after)
    if not state or request.args.get("state") != state:
        return render_template(
            "discord_error.html", error="the link was stale, please try again"
        )

    try:
        token = requests.post(
            f"{API}/oauth2/token",
            data={
                "grant_type": "authorization_code",
                "code": request.args.get("code"),
                "redirect_uri": _redirect_uri(),
            },
            auth=(config.DISCORD_CLIENT_ID, config.DISCORD_CLIENT_SECRET),
            timeout=10,
        )
        token.raise_for_status()
        access_token = token.json()["access_token"]
        user = requests.get(
            f"{API}/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        user.raise_for_status()
    except requests.RequestException as ex:
        log.warning(f"Discord would not identify the user: {ex}")
        return render_template(
            "discord_error.html", error="Discord did not confirm the account"
        )

    discord_user_id = int(user.json()["id"])
    discord_username = user.json()["username"]
    athlete_id = session["athlete_id"]
    db = meta.scoped_session()
    athlete = db.get(Athlete, athlete_id)
    if not athlete:
        return redirect(url_for("general.join"))

    # One Discord account, one athlete: linking it again moves it.
    db.query(Athlete).filter(
        Athlete.discord_user_id == discord_user_id, Athlete.id != athlete_id
    ).update({Athlete.discord_user_id: None, Athlete.discord_username: None})
    athlete.discord_user_id = discord_user_id
    athlete.discord_username = discord_username
    log.info(f"Athlete {athlete_id} linked Discord {discord_username}")

    if "guilds.join" in token.json().get("scope", "").split():
        _join_guild(discord_user_id, access_token)

    return redirect(after)


def _join_guild(discord_user_id, access_token):
    # Needs the bot in the server with Create Invite; 204 is already a member.
    try:
        response = requests.put(
            f"{API}/guilds/{config.DISCORD_GUILD_ID}/members/{discord_user_id}",
            json={"access_token": access_token},
            headers={"Authorization": f"Bot {config.DISCORD_BOT_TOKEN}"},
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException as ex:
        log.warning(f"Could not add Discord {discord_user_id} to the server: {ex}")


@blueprint.route("/unlink", methods=["POST"])
def unlink():
    athlete = meta.scoped_session().get(Athlete, session["athlete_id"])
    if athlete:
        athlete.discord_user_id = None
        athlete.discord_username = None
    return redirect(_after(request.form.get("next")))
