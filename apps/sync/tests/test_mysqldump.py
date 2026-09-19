"""Reading one table out of a mysqldump, without a database to load it into."""

import lzma

import pytest

from freezing.sync.utils.mysqldump import columns, rows

DDL = """CREATE TABLE `athletes` (
  `id` int NOT NULL,
  `name` varchar(1024) NOT NULL,
  `team_id` int DEFAULT NULL,
  `refresh_token` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `team_id` (`team_id`),
  CONSTRAINT `athletes_ibfk_1` FOREIGN KEY (`team_id`) REFERENCES `teams` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;{eol}"""

INSERT = (
    "INSERT INTO `athletes` VALUES "
    "(1,'Plain Name',99,'tok1'),"
    "(2,'glenn ☀️ √glenn',NULL,'tok2'),"
    "(3,'O\\'Brien, Pat',99,NULL),"
    "(4,'Quote \\\" and \\\\ back',99,'tok4'),"
    "(5,'Line\\nbreak',99,'tok5');{eol}"
)

# A table that must be stepped over, holding text that looks like our markers.
NOISE = (
    "CREATE TABLE `rides` (\n  `id` int NOT NULL\n) ENGINE=InnoDB;{eol}"
    "INSERT INTO `rides` VALUES "
    "(1),(2),(3);{eol}"
)


def dump(tmp_path, eol="\n", compress=False):
    text = (NOISE + DDL + INSERT + NOISE).format(eol=eol)
    if compress:
        path = tmp_path / "d.sql.xz"
        path.write_bytes(lzma.compress(text.encode()))
    else:
        path = tmp_path / "d.sql"
        path.write_text(text)
    return path


@pytest.mark.parametrize("eol", ["\n", "\r\n"])
def test_columns_ignore_keys_and_constraints(tmp_path, eol):
    """A run-on statement swallows the next table's columns as if they were ours."""
    assert columns(dump(tmp_path, eol), "athletes") == [
        "id",
        "name",
        "team_id",
        "refresh_token",
    ]


@pytest.mark.parametrize("eol", ["\n", "\r\n"])
@pytest.mark.parametrize("compress", [False, True])
def test_every_row_is_read(tmp_path, eol, compress):
    got = list(rows(dump(tmp_path, eol, compress), "athletes"))
    assert [r["id"] for r in got] == ["1", "2", "3", "4", "5"]


def test_a_name_cannot_be_paired_with_the_wrong_token(tmp_path):
    """The one mistake that must not happen: commas and quotes in names."""
    got = {r["name"]: r["refresh_token"] for r in rows(dump(tmp_path), "athletes")}
    assert got["Plain Name"] == "tok1"
    assert got["glenn ☀️ √glenn"] == "tok2"
    assert got["O'Brien, Pat"] is None
    assert got['Quote " and \\ back'] == "tok4"
    assert got["Line\nbreak"] == "tok5"


def test_null_is_none_not_the_word(tmp_path):
    got = {r["id"]: r for r in rows(dump(tmp_path), "athletes")}
    assert got["2"]["team_id"] is None
    assert got["3"]["refresh_token"] is None
    assert got["1"]["team_id"] == "99"


def test_a_missing_table_says_so(tmp_path):
    with pytest.raises(LookupError):
        columns(dump(tmp_path), "nosuchtable")
