"""Test that we can load the PhotoSync class with related libraries.

freezing-sync-photos was bombing at import once, so this test makes sure the
libraries it needs are all in place.
"""

from freezing.sync.data.photos import PhotoSync


def test_phtosync_instantiation():
    ps = PhotoSync()
    assert ps is not None
