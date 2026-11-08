from flask import Blueprint, render_template

from freezing.model import meta
from freezing.model.orm import Ride, RidePhoto
from freezing.web.autolog import log
from freezing.web.utils.paging import requested_page

blueprint = Blueprint("photos", __name__)


@blueprint.route("/")
def index():
    page_size = 60

    total_q = (
        meta.scoped_session()
        .query(RidePhoto)
        .join(Ride)
        .order_by(
            Ride.start_date.desc(),
            RidePhoto.id.asc(),
        )
    )
    num_photos = total_q.count()

    # Settled before the query is built, so that the page a reader is shown
    # and the page they are told they are on cannot disagree.
    page, offset, total_pages = requested_page(page_size, num_photos)
    log.debug(f"Page = {page}, offset={offset}, limit={page_size}")

    page_q = total_q.limit(page_size).offset(offset)

    return render_template(
        "photos.html",
        photos=page_q,
        page=page,
        total_pages=total_pages,
    )
