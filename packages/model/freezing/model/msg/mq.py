import enum
from datetime import datetime
from typing import Any, Dict, Optional

from marshmallow import fields

from freezing.model.msg import BaseMessage, BaseSchema
from freezing.model.msg.strava import AspectType


class DefinedTubes(enum.Enum):
    activity_update = "activity-update"


class ActivityUpdate(BaseMessage):
    """Represents a Webhook Event Subscription Update."""

    operation: Optional[AspectType] = None
    athlete_id: Optional[int] = None
    activity_id: Optional[int] = None
    event_time: Optional[datetime] = None
    updates: Optional[Dict[str, Any]] = None

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
