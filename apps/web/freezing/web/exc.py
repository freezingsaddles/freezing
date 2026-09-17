from freezing.common.teams import MultipleTeamsError, NoTeamsError  # noqa: F401


class InvalidAuthorizationToken(RuntimeError):
    pass


class CommandError(RuntimeError):
    pass


class DataEntryError(ValueError):
    pass


class ConfigurationError(RuntimeError):
    pass


class ObjectNotFound(RuntimeError):
    pass
