"""The rules of sponsored pointless prizes, written in Markdown on the site."""

from datetime import datetime, timezone

from markdown_it import MarkdownIt

from freezing.model import meta
from freezing.model.orm import PrizeRules
from freezing.web.config import config

# Raw HTML is off so that what a sponsor writes cannot carry script into the
# page; markdown-it also refuses javascript: and similar link targets.
_markdown = MarkdownIt("commonmark", {"html": False, "linkify": False}).enable(
    ["table", "strikethrough"]
)


def _link_open(self, tokens, idx, options, env):
    token = tokens[idx]
    href = str(token.attrGet("href") or "")
    if href.startswith(("http://", "https://", "//")):
        token.attrSet("target", "_blank")
        token.attrSet("rel", "noreferrer")
    return self.renderToken(tokens, idx, options, env)


_markdown.add_render_rule("link_open", _link_open)


def can_edit(athlete_id: int | None, sponsors: list[int] | None) -> bool:
    if not athlete_id:
        return False
    return athlete_id in config.CABAL or athlete_id in (sponsors or [])


def load_rules(kind: str, name: str) -> str | None:
    rules = meta.scoped_session().get(PrizeRules, (kind, name))
    return rules.rules if rules else None


def render_rules(markdown: str | None) -> str | None:
    return _markdown.render(markdown) if markdown else None


def save_rules(kind: str, name: str, markdown: str, athlete_id: int):
    sess = meta.scoped_session()
    rules = sess.get(PrizeRules, (kind, name))
    if rules is None:
        rules = PrizeRules(kind=kind, name=name)
        sess.add(rules)
    rules.rules = markdown
    rules.updated_by = athlete_id
    rules.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)


def rules_context(
    kind: str, name: str, sponsors: list[int] | None, athlete_id: int | None
) -> dict:
    """Return the template variables for a prize's Rules tab, shown only if sponsored."""
    if not sponsors:
        return {"rules_kind": None}
    markdown = load_rules(kind, name)
    return {
        "rules_kind": kind,
        "rules_name": name,
        "rules_markdown": markdown or "",
        "rules_html": render_rules(markdown),
        "rules_editable": can_edit(athlete_id, sponsors),
    }
