from freezing.common.teams import MultipleTeamsError, NoTeamsError  # noqa: F401


class ConfigurationError(RuntimeError):
    pass


class CommandError(RuntimeError):
    pass


class DataEntryError(ValueError):
    pass


class IneligibleActivity(ValueError):
    pass


class ActivityNotFound(RuntimeError):
    pass


class AthleteDeauthorized(RuntimeError):
    """The athlete has taken our authorisation back, and their tokens are gone.

    Strava does not tell us when a rider disconnects the application; the first
    we hear of it is a refresh token it will not honour. Nothing we do brings
    that authorisation back, so anything holding this athlete should give up on
    them rather than try again on the next pass.
    """
