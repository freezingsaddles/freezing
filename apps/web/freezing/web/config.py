import logging
import os
from datetime import datetime, timedelta, tzinfo
from importlib.metadata import version
from zoneinfo import ZoneInfo

from colorlog import ColoredFormatter
from envparse import env

from freezing.common.seasons import competition_end
from freezing.common.times import parse_instant

from .version import branch, build_date, commit

envfile = os.environ.get("APP_SETTINGS", os.path.join(os.getcwd(), ".env"))

if os.path.exists(envfile):
    env.read_envfile(envfile)

_basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


class Config:
    """
    Configuration for the application. These can be overridden by setting the appropriate environment variables.

    Refactored with the help of GitHub Copilot.
    """

    BEANSTALKD_HOST: str = env("BEANSTALKD_HOST", default="localhost")
    BEANSTALKD_PORT: str = env("BEANSTALKD_PORT", cast=int, default=11300)
    BIND_INTERFACE: str = env("BIND_INTERFACE", default="127.0.0.1")
    COMPETITION_TEAMS: list[int] = env("TEAMS", cast=list, subcast=int, default=[])
    COMPETITION_TITLE: str = env("COMPETITION_TITLE", default="Freezing Saddles")
    DEBUG: bool = env("DEBUG", cast=bool, default=False)
    # Environment (localdev, production, etc.)
    ENVIRONMENT: str = env("ENVIRONMENT", default="localdev")
    DISCORD_INVITATION: str = env(
        "DISCORD_INVITATION",
        "https://example.org/",
    )
    # The OAuth2 client of the Discord application Freezebot runs as. Unset,
    # the site does not offer to link Discord accounts.
    DISCORD_CLIENT_ID: str = env("DISCORD_CLIENT_ID", default="")
    DISCORD_CLIENT_SECRET: str = env("DISCORD_CLIENT_SECRET", default="")
    # With the bot token, linking an account also adds it to the server.
    DISCORD_BOT_TOKEN: str = env("DISCORD_BOT_TOKEN", default="")
    DISCORD_GUILD_ID: int = env(
        "DISCORD_GUILD_ID", cast=int, default=1443244420358213643
    )
    INSTANCE_PATH: str = env(
        "INSTANCE_PATH", default=os.path.join(_basedir, "data/instance")
    )
    # Directory to store leaderboard data
    LEADERBOARDS_DIR: str = env(
        "LEADERBOARDS_DIR", default=os.path.join(_basedir, "leaderboards")
    )
    MAIN_TEAM: int = env("MAIN_TEAM", cast=int)
    OBSERVER_TEAMS: list[int] = env(
        "OBSERVER_TEAMS", cast=list, subcast=int, default=[]
    )
    # The home page's registration card shows from here until the competition
    # starts; unset, it never shows. /register is reachable either way.
    REGISTRATION_DATE: datetime | None = env(
        "REGISTRATION_DATE",
        default="",
        postprocessor=lambda val: parse_instant(val) if val else None,
    )
    REGISTRATION_SITE: str = env("REGISTRATION_SITE", "https://freezingsaddles.info/")
    SECRET_KEY = env("SECRET_KEY")
    SQLALCHEMY_URL: str = env("SQLALCHEMY_URL")
    SQLALCHEMY_ROOT_URL: str = env("SQLALCHEMY_ROOT_URL", None)
    START_DATE: datetime = env("START_DATE", postprocessor=parse_instant)
    STRAVA_CLIENT_ID = env("STRAVA_CLIENT_ID")
    STRAVA_CLIENT_SECRET = env("STRAVA_CLIENT_SECRET")
    JSON_CACHE_DIR = env("JSON_CACHE_DIR", default="/cache/json")
    JSON_CACHE_MINUTES = env("JSON_CACHE_MINUTES", cast=int, default=30)
    TRACK_LIMIT_DEFAULT = env("TRACK_LIMIT_DEFAULT", cast=int, default=1024)
    TRACK_LIMIT_MAX = env("TRACK_LIMIT_MAX", cast=int, default=2048)
    TIMEZONE: tzinfo = env(
        "TIMEZONE",
        default="America/New_York",
        postprocessor=lambda val: ZoneInfo(val),
    )
    # A winter competition ends when winter does. Left unset, that is worked
    # out rather than written down again every year.
    END_DATE: datetime = competition_end(
        env("END_DATE", default=None), START_DATE, TIMEZONE
    )
    VERSION_NUM: str = version("freezing-web")
    VERSION_STRING: str = f"{VERSION_NUM}+{branch}.{commit}.{build_date}"
    SEND_FILE_MAX_AGE_DEFAULT: int | None = (
        None
        if ENVIRONMENT == "localdev"
        else 84600  # let the browser cache static files for 24 hours
    )
    # From registration start (Thanksgiving) until shortly after the competition ends.
    PERMANENT_SESSION_LIFETIME: timedelta = timedelta(days=128)


config = Config()


def init_logging(loglevel: int = logging.INFO, color: bool = False):
    """
    Initialize the logging subsystem and create a logger for this class, using passed in optparse options.

    :param level: The log level (e.g. logging.DEBUG)
    :return:
    """
    ch = logging.StreamHandler()
    ch.setLevel(loglevel)

    formatter: logging.Formatter
    if color:
        formatter = ColoredFormatter(
            "%(log_color)s%(levelname)-8s%(reset)s [%(name)s] %(message)s",
            datefmt=None,
            reset=True,
            log_colors={
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "red",
            },
        )
    else:
        formatter = logging.Formatter("%(levelname)-8s [%(name)s] %(message)s")

    ch.setFormatter(formatter)

    log_level_map = {
        "freezing": logging.DEBUG,
        "requests": logging.INFO,
        "stravalib": logging.INFO,
        "root": logging.DEBUG,
    }
    loggers = {k: logging.getLogger(k) for k in log_level_map.keys()}
    loggers.update({"root": logging.root})

    for k, logger in loggers.items():
        logger.setLevel(log_level_map[k])

    logging.root.addHandler(ch)

    logger.info(f"loggers: {loggers}")
    logger.info(f"logging initialized for app version {config.VERSION_STRING}")
