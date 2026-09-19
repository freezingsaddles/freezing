"""Read one table out of a mysqldump, without a database to load it into.

A season's dump is a gigabyte of rides and GPS tracks around a few hundred
athletes, so this looks for one table's statements and steps over the rest
without holding them in memory.
"""

import lzma
import re
from collections.abc import Iterator
from pathlib import Path
from typing import IO

# mysqldump writes one statement per line, so a line is the unit of work, but a
# line can be hundreds of megabytes. Read in pieces and keep only what matters.
_CHUNK = 1 << 20

# Dumps have been written with both line endings over the years, and a statement
# that does not end where it should runs on into the next table.
_END = re.compile(rb";\r?\n")

_ESCAPES = {
    "0": "\0",
    "b": "\b",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "Z": "\x1a",
    "\\": "\\",
    "'": "'",
    '"': '"',
}


def _open(path: Path) -> IO[bytes]:
    return lzma.open(path, "rb") if path.suffix == ".xz" else path.open("rb")


def _statements(path: Path, prefix: bytes) -> Iterator[str]:
    """Yield whole statements beginning with `prefix`, discarding everything else."""
    with _open(path) as fp:
        held = b""
        keeping = False
        while chunk := fp.read(_CHUNK):
            held += chunk
            while True:
                if keeping:
                    end = _END.search(held)
                    if end is None:
                        break
                    yield held[: end.start()].decode("utf-8", "replace")
                    held = held[end.end() :]
                    keeping = False
                else:
                    start = held.find(prefix)
                    if start == -1:
                        # Keep only enough to catch a prefix split across reads.
                        held = held[-len(prefix) :]
                        break
                    held = held[start:]
                    keeping = True
        if keeping and held:
            yield held.decode("utf-8", "replace")


def columns(path: Path, table: str) -> list[str]:
    """Return the table's columns, in the order its INSERT statements use."""
    for statement in _statements(path, f"CREATE TABLE `{table}` (".encode()):
        # A key or constraint line starts with a word, a column line with its
        # own name, so requiring the backtick first picks out the columns.
        return re.findall(r"^\s+`([^`]+)`", statement, re.M)
    raise LookupError(f"no CREATE TABLE for {table!r} in {path}")


def _values(text: str) -> Iterator[list[str | None]]:
    """Walk the tuples of an INSERT's VALUES clause.

    Written out rather than split on punctuation because a rider's name may
    hold a comma, a quote or an emoji, and pairing the wrong name with the
    wrong token is the one mistake that must not happen here.
    """
    i = 0
    row: list[str | None] = []
    field: str | None = None
    while i < len(text):
        c = text[i]
        if c == "(" and field is None and not row:
            row = []
            i += 1
        elif c == "'":
            i += 1
            out = []
            while text[i] != "'":
                if text[i] == "\\":
                    out.append(_ESCAPES.get(text[i + 1], text[i + 1]))
                    i += 2
                else:
                    out.append(text[i])
                    i += 1
            field = "".join(out)
            i += 1
        elif c in ",)":
            if field is not None:
                row.append(field)
                field = None
            if c == ")":
                yield row
                row = []
                # Skip to the next tuple.
                nxt = text.find("(", i)
                i = len(text) if nxt == -1 else nxt
            else:
                i += 1
        elif c.isspace():
            i += 1
        else:
            end = min(
                (p for p in (text.find(",", i), text.find(")", i)) if p != -1),
                default=len(text),
            )
            literal = text[i:end].strip()
            row.append(None if literal.upper() == "NULL" else literal)
            i = end
    return


def rows(path: Path, table: str) -> Iterator[dict[str, str | None]]:
    """Every row of `table`, as a mapping from column name to value."""
    names = columns(path, table)
    for statement in _statements(path, f"INSERT INTO `{table}` VALUES".encode()):
        clause = statement.split("VALUES", 1)[1]
        for row in _values(clause):
            yield dict(zip(names, row, strict=True))
