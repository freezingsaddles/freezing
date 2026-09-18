import os
from collections import defaultdict

import yaml
from marshmallow import fields

from freezing.model import meta
from freezing.model.msg import BaseMessage, BaseSchema
from freezing.model.orm import Tribe
from freezing.web.config import config
from freezing.web.exc import ObjectNotFound


class TribalGroup(BaseMessage):
    name = None
    id = None
    tribes: list[str] | None = None


class TribalGroupSchema(BaseSchema):
    _model_class = TribalGroup

    name = fields.Str(required=True)
    id = fields.Str(required=True)
    tribes = fields.List(fields.Str())


class TribalGroups(BaseMessage):
    tribal_groups: list[TribalGroup] | None = None


class TribalGroupsSchema(BaseSchema):
    _model_class = TribalGroups

    tribal_groups = fields.Nested(TribalGroupSchema, many=True, required=True)


def load_tribes() -> list[TribalGroup]:
    path = os.path.join(config.LEADERBOARDS_DIR, "tribes.yml")
    if not os.path.exists(path):
        raise ObjectNotFound(f"Could not find tribes definition {path}")

    with open(path, encoding="utf-8") as fp:
        doc = yaml.safe_load(fp)

    schema = TribalGroupsSchema()
    groups: TribalGroups = schema.load(doc)

    if groups.tribal_groups is None:
        raise ObjectNotFound(f"No tribal_groups in tribes definition {path}")

    return groups.tribal_groups


def query_tribes(athlete_id):
    tribes_q = meta.scoped_session().query(Tribe).filter(Tribe.athlete_id == athlete_id)

    my_tribes = defaultdict(str)
    for r in tribes_q:
        my_tribes[r.tribal_group] = r.tribe_name

    return my_tribes
