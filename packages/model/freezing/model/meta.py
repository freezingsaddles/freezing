"""SQLAlchemy Metadata and Session object."""

import contextlib
from typing import Iterator, Optional

from sqlalchemy import MetaData, orm
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

# SQLAlchemy database engine.  None until model.init_model() sets it.
engine: Optional[Engine] = None

# SQLAlchemy session manager.  None until model.init_model() sets it, but
# typed as the real thing: every caller runs after init_model(), and the
# tests patch this attribute, so it must exist at import time.
scoped_session: orm.scoped_session[Session] = None  # type: ignore[assignment]

# Global metadata. If you have multiple databases with overlapping table
# names, you'll need a metadata for each database
metadata = MetaData()


@contextlib.contextmanager
def transaction_context(read_only: bool = False) -> Iterator[Session]:
    session = scoped_session()
    try:
        yield session
    except BaseException:  # an interrupt mid-transaction must roll back too
        session.rollback()
        raise
    else:
        if read_only:
            session.rollback()
        else:
            session.commit()
    finally:
        session.close()
