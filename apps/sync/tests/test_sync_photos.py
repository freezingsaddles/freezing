"""Test that we can load the PhotoSync class with related libraries.

freezing-sync-photos was bombing at import once, so this test makes sure the
libraries it needs are all in place.
"""

import subprocess
import sys

from freezing.sync.data.photos import PhotoSync


def test_phtosync_instantiation():
    ps = PhotoSync()
    assert ps is not None


PROBE = """
from freezing.model.orm import Ride

print(Ride.athlete.has())
"""


def test_the_query_can_filter_on_the_athlete_of_a_ride():
    """sync_photos selects a column, so nothing has configured the mappers yet.

    A relationship declared as a backref is only attached to the far class at
    that point, so filtering on Ride.athlete raised AttributeError. Ask for it
    in a fresh interpreter, where no other query has configured anything.
    """
    probe = subprocess.run(
        [sys.executable, "-c", PROBE], capture_output=True, text=True
    )
    assert probe.returncode == 0, probe.stderr
    assert "athletes.id = rides.athlete_id" in probe.stdout
