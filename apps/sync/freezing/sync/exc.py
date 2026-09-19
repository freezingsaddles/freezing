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
    """We hold no authorisation for this athlete, and asking again will not help."""
