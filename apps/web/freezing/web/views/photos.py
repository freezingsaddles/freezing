import math

from flask import Blueprint, render_template, request
from sqlalchemy import func

from freezing.model import meta
from freezing.model.orm import Ride, RidePhoto
from freezing.web.autolog import log

blueprint = Blueprint("photos", __name__)


@blueprint.route("/")
def index():
    page = int(request.args.get("page", 1))
    if page < 1:
        page = 1

    page_size = 60
    offset = page_size * (page - 1)
    limit = page_size

    log.debug(f"Page = {page}, offset={offset}, limit={limit}")

    total_q = (
        meta.scoped_session()
        .query(RidePhoto)
        .join(Ride)
        .order_by(
            func.convert_tz(Ride.start_date, Ride.timezone, "GMT").desc(),
            RidePhoto.id.asc(),
        )
    )
    num_photos = total_q.count()

    page_q = total_q.limit(limit).offset(offset)

    if num_photos < offset:
        page = 1

    total_pages = int(math.ceil((1.0 * num_photos) / page_size))

    if page > total_pages:
        page = total_pages

    return render_template(
        "photos.html",
        photos=page_q,
        page=page,
        total_pages=total_pages,
    )
