import enum
from datetime import datetime
from typing import Any

from marshmallow import fields

from freezing.model.msg import BaseMessage, BaseSchema
from freezing.model.msg.strava import AspectType


class DefinedTubes(enum.Enum):
    activity_update = "activity-update"
    athlete_update = "athlete-update"


class ActivityUpdate(BaseMessage):
    """Represents a Webhook Event Subscription Update."""

    operation: AspectType | None = None
    athlete_id: int | None = None
    activity_id: int | None = None
    event_time: datetime | None = None
    updates: dict[str, Any] | None = None

    def __repr__(self):
        return "[Activity {} id={} athlete={}]".format(
            self.operation.value if self.operation else "?",
            self.activity_id,
            self.athlete_id,
        )


class ActivityUpdateSchema(BaseSchema):
    """Represents a Webhook Event Subscription Update."""

    _model_class = ActivityUpdate

    operation = fields.Enum(AspectType)
    athlete_id = fields.Int()
    activity_id = fields.Int()
    event_time = fields.DateTime()
    updates = fields.Dict()


class AthleteUpdate(BaseMessage):
    """Represents a change to an athlete rather than to one of their rides.

    Strava defines one such change: the rider disconnecting the application,
    which arrives as an update carrying ``authorized: "false"``.
    """

    operation: AspectType | None = None
    athlete_id: int | None = None
    event_time: datetime | None = None
    updates: dict[str, Any] | None = None

    @property
    def deauthorized(self) -> bool:
        """Say whether the rider has handed our authorisation back."""
        return (self.updates or {}).get("authorized") == "false"

    def __repr__(self):
        return "[Athlete {} id={}{}]".format(
            self.operation.value if self.operation else "?",
            self.athlete_id,
            " deauthorized" if self.deauthorized else "",
        )


class AthleteUpdateSchema(BaseSchema):
    """Something has changed about an athlete rather than about a ride."""

    _model_class = AthleteUpdate

    operation = fields.Enum(AspectType)
    athlete_id = fields.Int()
    event_time = fields.DateTime()
    updates = fields.Dict()
