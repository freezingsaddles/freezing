"""stravalib warns on every call that we did not hand it our refresh token."""

import logging

import pytest

from freezing.sync.config import _WithoutAutoRefreshWarning


def record(module, func, message="something", level=logging.WARNING):
    made = logging.LogRecord("root", level, f"/x/{module}.py", 1, message, None, None)
    made.module = module
    made.funcName = func
    return made


@pytest.fixture
def filter_():
    return _WithoutAutoRefreshWarning()


def test_the_warning_is_dropped(filter_):
    assert not filter_.filter(
        record(
            "protocol",
            "refresh_expired_token",
            "Please set client.refresh_token if you want to usethe auto "
            "token-refresh feature",
        )
    )


@pytest.mark.parametrize(
    "module,func",
    [
        # Everything else stravalib's protocol says, including the faults that
        # tell us a rider disconnected.
        ("protocol", "_handle_protocol_error"),
        ("protocol", "refresh_access_token"),
        ("protocol", "_request"),
        # A module of ours that happens to share the name.
        ("protocol", "some_function_of_ours"),
        ("activity", "sync_rides_detail"),
        ("photos", "sync_photos"),
    ],
)
def test_everything_else_survives(filter_, module, func):
    assert filter_.filter(record(module, func))


def test_it_is_installed_on_the_handler():
    from freezing.sync.config import init_logging

    logging.root.handlers = []
    init_logging()
    installed = [
        f
        for handler in logging.root.handlers
        for f in handler.filters
        if isinstance(f, _WithoutAutoRefreshWarning)
    ]
    assert installed
