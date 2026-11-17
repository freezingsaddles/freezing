import enum
from datetime import UTC, datetime
from typing import Any

from marshmallow import fields, pre_load

from . import BaseMessage, BaseSchema


class ObjectType(enum.Enum):
    activity = "activity"
    athlete = "athlete"


class AspectType(enum.Enum):
    create = "create"
    update = "update"
    delete = "delete"


class Subscription(BaseMessage):
    """
    Represents a Webhook Event Subscription.

    http://strava.github.io/api/partner/v3/events/
    """

    application_id: int | None = None
    object_type: ObjectType | None = None
    aspect_type: AspectType | None = None
    callback_url: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SubscriptionSchema(BaseSchema):
    """
    Represents a Webhook Event Subscription.

    http://strava.github.io/api/partner/v3/events/
    """

    _model_class = Subscription

    application_id = fields.Int()
    object_type = fields.Enum(ObjectType)
    aspect_type = fields.Enum(AspectType)
    callback_url = fields.Str()
    created_at = fields.DateTime()
    updated_at = fields.DateTime()


class SubscriptionCallback(BaseMessage):
    """Represents a Webhook Event Subscription Callback."""

    hub_mode: str | None = None
    hub_verify_token: str | None = None
    hub_challenge: str | None = None


class SubscriptionCallbackSchema(BaseSchema):
    """Represents a Webhook Event Subscription Callback."""

    _model_class = SubscriptionCallback

    hub_mode = fields.Str(data_key="hub.mode")
    hub_verify_token = fields.Str(data_key="hub.verify_token")
    hub_challenge = fields.Str(data_key="hub.challenge")


class SubscriptionUpdate(BaseMessage):
    """Represents a Webhook Event Subscription Update."""

    subscription_id: int | None = None
    owner_id: int | None = None
    object_id: int | None = None
    object_type: ObjectType | None = None
    # The schema loads this with fields.Enum(AspectType), not as a str.
    aspect_type: AspectType | None = None
    event_time: datetime | None = None
    updates: dict[str, Any] | None = None


class SubscriptionUpdateSchema(BaseSchema):
    """Represents a Webhook Event Subscription Update."""

    _model_class = SubscriptionUpdate

    subscription_id = fields.Int()
    owner_id = fields.Int()
    object_id = fields.Int()
    object_type = fields.Enum(ObjectType)
    aspect_type = fields.Enum(AspectType)
    event_time = fields.DateTime()
    updates = fields.Dict()

    @pre_load
    def parse_dt(self, in_data, **kwargs):
        # Strava sends this as seconds since the epoch; anything already written
        # out is left for the field itself to read.
        event_time = in_data.get("event_time")
        if isinstance(event_time, (int, float)):
            in_data["event_time"] = datetime.fromtimestamp(event_time, UTC).isoformat()
        return in_data
