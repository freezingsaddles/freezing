"""Read the page number a request asks for."""

import math

from flask import abort, request


def requested_page(page_size: int, total: int) -> tuple[int, int, int]:
    """Return the page asked for, where it starts, and how many there are.

    A page beyond the last one is not a page, so it is a 404 rather than an
    empty gallery labelled as some other page. Crawlers walk these addresses
    by the thousand and have nothing else to tell them where the end is.

    An empty collection still has a first page, so that a season which has
    had no photos yet says so instead of refusing to open.
    """
    asked = request.args.get("page", "1")
    try:
        page = int(asked)
    except ValueError:
        abort(404, f"page {asked!r} is not a number")

    total_pages = max(1, int(math.ceil(total / page_size)))
    if page < 1 or page > total_pages:
        abort(404, f"there is no page {page}")

    return page, page_size * (page - 1), total_pages
