import enum
from datetime import datetime
from typing import Any, Dict, Optional

import arrow
from marshmallow import fields, pre_load

from . import BaseMessage, BaseSchema


class ObjectType(enum.Enum):
    activity = "activity"


class AspectType(enum.Enum):
    create = "create"
    update = "update"
    delete = "delete"


class Subscription(BaseMessage):
    """
    Represents a Webhook Event Subscription.

    http://strava.github.io/api/partner/v3/events/
    """

    application_id: Optional[int] = None
    object_type: Optional[ObjectType] = None
    aspect_type: Optional[AspectType] = None
    callback_url: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


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

    hub_mode: Optional[str] = None
    hub_verify_token: Optional[str] = None
    hub_challenge: Optional[str] = None


class SubscriptionCallbackSchema(BaseSchema):
    """Represents a Webhook Event Subscription Callback."""

    _model_class = SubscriptionCallback

    hub_mode = fields.Str(data_key="hub.mode")
    hub_verify_token = fields.Str(data_key="hub.verify_token")
    hub_challenge = fields.Str(data_key="hub.challenge")


class SubscriptionUpdate(BaseMessage):
    """Represents a Webhook Event Subscription Update."""

    subscription_id: Optional[int] = None
    owner_id: Optional[int] = None
    object_id: Optional[int] = None
    object_type: Optional[ObjectType] = None
    # The schema loads this with fields.Enum(AspectType), not as a str.
    aspect_type: Optional[AspectType] = None
    event_time: Optional[datetime] = None
    updates: Optional[Dict[str, Any]] = None


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
        if in_data.get("event_time"):
            in_data["event_time"] = arrow.get(in_data["event_time"]).isoformat()
        return in_data
