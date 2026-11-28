"""Where registered contestants live, as blobs on a map rather than pins."""

import csv
import gzip
from collections import Counter
from functools import cache
from pathlib import Path

from sqlalchemy import text

from freezing.model import meta

# Below this a blob could be one rider a reader knows, so there is no map.
MINIMUM = 16


@cache
def _centroids() -> dict[str, tuple[float, float]]:
    # GeoNames' US postal codes (CC BY 4.0): the middle of each zip code.
    path = Path(__file__).parent.parent / "geo" / "zip-centroids.csv.gz"
    with gzip.open(path, "rt", newline="") as f:
        return {
            row["zip"]: (float(row["lat"]), float(row["lon"]))
            for row in csv.DictReader(f)
        }


def registered_points() -> dict | None:
    """Where registered contestants live, by zip code centre, in the order they registered.

    ``start`` is the first MINIMUM riders who can be placed, as places and counts in no
    particular order; ``then`` is each later rider's place, one at a time. None while
    fewer than MINIMUM can be placed. No zip code or registration time leaves here.
    """
    q = text("""
             select left(trim(R.zip_code), 5) as zip
             from registrations R
             join athletes A on A.id = R.athlete_id
             where A.registered and not coalesce(A.friend, false)
             order by R.registered_at, R.athlete_id
             """)
    centroids = _centroids()
    placed = [
        centroids[row.zip]
        for row in meta.scoped_session().execute(q)
        if row.zip in centroids
    ]
    if len(placed) < MINIMUM:
        return None
    start = Counter(placed[:MINIMUM])
    return {
        "start": [(lat, lon, riders) for (lat, lon), riders in sorted(start.items())],
        "then": [(lat, lon) for lat, lon in placed[MINIMUM:]],
    }
