import json

import falcon

from freezing.model.msg.mq import (
    ActivityUpdate,
    ActivityUpdateSchema,
    AthleteUpdate,
    AthleteUpdateSchema,
    DefinedTubes,
)
from freezing.model.msg.strava import (
    ObjectType,
    SubscriptionCallback,
    SubscriptionCallbackSchema,
    SubscriptionUpdate,
    SubscriptionUpdateSchema,
)
from freezing.nq.autolog import log
from freezing.nq.config import config
from freezing.nq.publish import ActivityPublisher


class WebhookResource:
    def __init__(self, publisher: ActivityPublisher):
        self.publisher = publisher

    def on_get(self, req: falcon.Request, resp: falcon.Response):
        """
        Validate this endpoint for Strava, which sends the GET request when the webhook is initially registered.

        See: https://developers.strava.com/docs/webhooks/
        """
        strava_request = {
            k: req.get_param(k)
            for k in ("hub.challenge", "hub.mode", "hub.verify_token")
        }
        schema = SubscriptionCallbackSchema()
        callback: SubscriptionCallback = schema.load(strava_request)

        if config.STRAVA_VERIFY_TOKEN != callback.hub_verify_token:
            raise falcon.HTTPForbidden(description="hub.verify_token invalid")
        resp.status = falcon.HTTP_200
        resp.text = json.dumps({"hub.challenge": callback.hub_challenge})

    def on_post(self, req: falcon.Request, resp: falcon.Response):
        """
        Receives a POST request (webhook) from Strava to indicate that an activity has been created or updated.

        We use stravalib to deserialize this (although the structure is pretty trivial).
        This will the be published to beanstalkd (etc.) for picking up by main processing component.

        Message payload:
                subscription_id = Attribute(str)
                owner_id = Attribute(str)
                object_id = Attribute(str)
                object_type = Attribute(str)
                aspect_type = Attribute(str)
                event_time = TimestampAttribute()

        See: https://developers.strava.com/docs/webhooks/
        """
        schema = SubscriptionUpdateSchema()
        result: SubscriptionUpdate = schema.load(req.media)

        if result.object_type is ObjectType.activity:
            message = ActivityUpdate()
            message.athlete_id = result.owner_id
            message.event_time = result.event_time
            message.activity_id = result.object_id
            message.operation = result.aspect_type
            message.updates = result.updates

            json_data = ActivityUpdateSchema().dump(message)

            log.info(f"Publishing activity-update: {message}")
            self.publisher.publish_message(json_data, dest=DefinedTubes.activity_update)
        elif result.object_type is ObjectType.athlete:
            # The one athlete event Strava defines is the rider disconnecting
            # us, and it is the only notice we get that their tokens are dead.
            message = AthleteUpdate()
            message.athlete_id = result.owner_id
            message.event_time = result.event_time
            message.operation = result.aspect_type
            message.updates = result.updates

            json_data = AthleteUpdateSchema().dump(message)

            log.info(f"Publishing athlete-update: {message}")
            self.publisher.publish_message(json_data, dest=DefinedTubes.athlete_update)
        else:
            log.info(f"Ignoring webhook we have no use for: {req.media}")
