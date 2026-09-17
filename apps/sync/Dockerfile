# Build from the workspace root: docker build -f apps/sync/Dockerfile .
FROM python:3.10-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /bin/uv
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# Dependencies first so they cache independently of app source changes.
COPY pyproject.toml uv.lock .python-version ./
COPY packages/model/pyproject.toml packages/model/
COPY packages/common/pyproject.toml packages/common/
COPY apps/web/pyproject.toml apps/web/
COPY apps/sync/pyproject.toml apps/sync/
COPY apps/nq/pyproject.toml apps/nq/
RUN uv sync --frozen --no-dev --no-install-workspace --package freezing-sync

COPY packages/model packages/model
COPY packages/common packages/common
COPY apps/sync apps/sync
RUN uv sync --frozen --no-dev --no-editable --package freezing-sync

FROM python:3.10-slim
RUN mkdir -p /data/cache/activities /data/cache/weather
VOLUME /data
COPY --from=build /app/.venv /app/.venv
COPY apps/sync/alembic.ini /app/alembic.ini
ENV PATH="/app/.venv/bin:$PATH"
WORKDIR /app
CMD ["freezing-sync"]
