"""Read one table out of a mysqldump, without a database to load it into.

A season's dump is a gigabyte of rides and GPS tracks around a few hundred
athletes, so this looks for one table's statements and steps over the rest
without holding them in memory.

A dump can also arrive on a pipe, which is how it reaches a container that
cannot see the backups. That is read once, front to back, so the table's
definition has to be taken as it goes past rather than looked up afterwards.
"""

import lzma
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import IO, Protocol, cast

#: Stand-in for standard input, as a command-line argument.
STDIN = Path("-")

_XZ_MAGIC = b"\xfd7zXZ\x00"

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


class _Readable(Protocol):
    """All a dump is asked for: the next so many bytes."""

    def read(self, size: int = -1, /) -> bytes:
        """Return up to __TEXT	__DATA	__OBJC	others	dec	hex bytes, or everything left when it is negative."""


class _Rejoined:
    """A stream with its first bytes put back, so a pipe can be sniffed."""

    def __init__(self, head: bytes, rest: _Readable):
        self._head = head
        self._rest = rest

    def read(self, size: int = -1) -> bytes:
        if not self._head:
            return self._rest.read(size)
        out, self._head = self._head, b""
        return out + (self._rest.read(size - len(out)) if size > 0 else b"")


def _open(path: Path) -> _Readable:
    """Open a dump, compressed or not, from a file or from standard input."""
    if path != STDIN:
        return lzma.open(path, "rb") if path.suffix == ".xz" else path.open("rb")
    # A pipe cannot be rewound, so sniff the magic and hand it back.
    stream: _Readable = sys.stdin.buffer
    head = stream.read(len(_XZ_MAGIC))
    rejoined = _Rejoined(head, stream)
    if head != _XZ_MAGIC:
        return rejoined
    return lzma.open(cast(IO[bytes], rejoined), "rb")


def _statements(
    source: Path | _Readable, prefixes: list[bytes]
) -> Iterator[tuple[int, str]]:
    """Yield each statement starting with one of `prefixes`, and which it was.

    In the order they appear, so one pass serves a reader that cannot go back.
    """
    fp = _open(source) if isinstance(source, Path) else source
    held = b""
    keeping = -1
    while chunk := fp.read(_CHUNK):
        held += chunk
        while True:
            if keeping >= 0:
                end = _END.search(held)
                if end is None:
                    break
                yield keeping, held[: end.start()].decode("utf-8", "replace")
                held = held[end.end() :]
                keeping = -1
            else:
                found = [
                    (at, n)
                    for n, p in enumerate(prefixes)
                    if (at := held.find(p)) != -1
                ]
                if not found:
                    # Keep only enough to catch a prefix split across reads.
                    held = held[-max(len(p) for p in prefixes) :]
                    break
                start, keeping = min(found)
                held = held[start:]
    if keeping >= 0 and held:
        yield keeping, held.decode("utf-8", "replace")


def columns(path: Path, table: str) -> list[str]:
    """Return the table's columns, in the order its INSERT statements use."""
    for _, statement in _statements(path, [f"CREATE TABLE `{table}` (".encode()]):
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
    """Every row of `table`, as a mapping from column name to value.

    One pass: mysqldump writes a table's definition before its rows, so the
    column names are in hand by the time the first of them arrives.
    """
    names: list[str] = []
    prefixes = [
        f"CREATE TABLE `{table}` (".encode(),
        f"INSERT INTO `{table}` VALUES".encode(),
    ]
    for which, statement in _statements(path, prefixes):
        if which == 0:
            # A key or constraint line starts with a word, a column line with
            # its own name, so requiring the backtick first picks out the
            # columns.
            names = re.findall(r"^\s+`([^`]+)`", statement, re.M)
            continue
        if not names:
            raise LookupError(f"rows of {table!r} arrived before its definition")
        for row in _values(statement.split("VALUES", 1)[1]):
            yield dict(zip(names, row, strict=True))
