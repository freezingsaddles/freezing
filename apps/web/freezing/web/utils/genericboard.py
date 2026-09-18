import decimal
import os
from datetime import datetime
from typing import Any, Dict, List, Tuple

import yaml
from marshmallow import fields
from sqlalchemy import text

from freezing.model import meta
from freezing.model.msg import BaseMessage, BaseSchema
from freezing.web.config import config
from freezing.web.exc import ObjectNotFound


class GenericBoardField(BaseMessage):
    name = None
    label = None
    type = None  # Do we need this ...?  Yes, for formatting, for alignment.
    format = None
    formatx = None
    visible: bool = True
    rank_by: bool = False

    def format_value(self, v, row):
        if isinstance(v, str):
            if self.format:
                return self.format.format(**dict(row._mapping))
            return v

        if isinstance(v, (float, decimal.Decimal)):
            # The format is a str.format spec such as a fixed number of digits
            # or a thousands separator.
            if self.formatx:
                return self.formatx.format(**dict(row._mapping))
            if self.format:
                return self.format.format(v)
            return "{0:,.2f}".format(v)

        if isinstance(v, int):
            # The format is a str.format spec such as a thousands separator.
            if self.format:
                return self.format.format(v)
            return "{0:,}".format(v)

        if isinstance(v, datetime):
            if self.format:
                return v.strftime(self.format)
            return v.isoformat()

        return v


class GenericBoardFieldSchema(BaseSchema):
    _model_class = GenericBoardField

    name = fields.Str()
    label = fields.Str()
    type = fields.Str()
    format = fields.Str()
    formatx = fields.Str()
    sponsor = fields.Str()
    visible = fields.Bool()
    rank_by = fields.Bool()


class GenericBoard(BaseMessage):
    title = None
    name = None  # used in the menu
    description = None
    url = None
    discord: int | None = None
    sponsors: List[int] | None = None
    banned: List[int] | None = None  # banned for prior win
    query: str | None = None
    fields: List[GenericBoardField] | None = None


class GenericBoardSchema(BaseSchema):
    _model_class = GenericBoard

    title = fields.Str()
    name = fields.Str()
    description = fields.Str()
    url = fields.Str()
    discord = fields.Int()
    sponsors = fields.List(fields.Int())
    banned = fields.List(fields.Int())
    query = fields.Str(required=True, allow_none=False)
    fields = fields.Nested(GenericBoardFieldSchema, many=True, required=False)


def load_board_and_data(leaderboard) -> Tuple[GenericBoard, List[Dict[str, Any]]]:
    board = load_board(leaderboard)
    if board.query is None:
        raise ObjectNotFound("Board {} has no query".format(leaderboard))

    with meta.transaction_context(read_only=True) as session:
        rs = session.execute(text(board.query))

        if not board.fields:
            board.fields = [GenericBoardField(name=k, label=k) for k in rs.keys()]

        rows = rs.fetchall()

        return board, format_rows(rows, board)


def load_board(leaderboard) -> GenericBoard:
    path = os.path.join(
        config.LEADERBOARDS_DIR, "{}.yml".format(os.path.basename(leaderboard))
    )
    if not os.path.exists(path):
        raise ObjectNotFound("Could not find yaml board definition {}".format(path))

    with open(path, "rt", encoding="utf-8") as fp:
        doc = yaml.safe_load(fp)

    schema = GenericBoardSchema()
    board: GenericBoard = schema.load(doc)

    return board


def format_rows(rows, board) -> List[Dict[str, Any]]:
    banned = []
    if board.sponsors:
        banned.extend(board.sponsors)
    if board.banned:
        banned.extend(board.banned)

    def format_athlete(row):
        athlete_id = row._mapping["athlete_id"]
        template = (
            '<a href="/people/{id}" class="hover-underline text-muted">{name} <em>(ineligible)</em></a>'
            if athlete_id in banned
            else '<a href="/people/{id}" class="hover-underline">{name}</a>'
        )
        return template.format(id=athlete_id, name=row._mapping["athlete_name"])

    def format_team(row):
        template = '<a href="/teams/{id}" class="hover-underline">{name}</a>'
        return template.format(
            id=row._mapping["team_id"], name=row._mapping["team_name"]
        )

    def format_field(f: GenericBoardField, row) -> str:
        if f.type == "athlete":
            return format_athlete(row)
        if f.type == "team":
            return format_team(row)
        return f.format_value(row._mapping[f.name], row)

    try:
        formatted = [
            {f.name: format_field(f, row) for f in board.fields} for row in rows
        ]
        rank_by = next(iter([f.name for f in board.fields if f.rank_by]), None)
        return formatted if rank_by is None else rank_rows(formatted, rank_by)
    except KeyError as ke:
        raise RuntimeError("Field not found in result row: {}".format(ke)) from ke


def rank_rows(rows, rank_by, index=1, rank=0, rank_value=None) -> List[Dict[str, Any]]:
    if len(rows) == 0:
        return rows
    head, *tail = rows
    head_value = head[rank_by]
    head_rank = rank if index > 1 and head_value == rank_value else index
    return [{**head, "rank": head_rank}] + rank_rows(
        tail, rank_by, 1 + index, head_rank, head_value
    )
