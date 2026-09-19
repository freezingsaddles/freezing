"""Read the instants that people and configuration files hand us."""

from datetime import UTC, datetime


def parse_instant(text: str) -> datetime:
    """
    Return an aware datetime for an ISO 8601 date or timestamp.

    A value written without an offset is read as UTC rather than as the wall
    clock of whichever machine happens to run this.
    """
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
