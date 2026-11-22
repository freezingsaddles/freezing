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


def registered_points() -> list[tuple[float, float, int]]:
    """Each place registered contestants live, and how many, by zip code centre.

    Empty while fewer than MINIMUM can be placed. No zip code leaves here.
    """
    q = text("""
             select left(trim(R.zip_code), 5) as zip, count(*) as riders
             from registrations R
             join athletes A on A.id = R.athlete_id
             where A.registered and not coalesce(A.friend, false)
             group by left(trim(R.zip_code), 5)
             """)
    centroids = _centroids()
    places: Counter[tuple[float, float]] = Counter()
    for row in meta.scoped_session().execute(q):
        place = centroids.get(row.zip)
        if place:
            places[place] += row.riders
    if places.total() < MINIMUM:
        return []
    return [(lat, lon, riders) for (lat, lon), riders in sorted(places.items())]
