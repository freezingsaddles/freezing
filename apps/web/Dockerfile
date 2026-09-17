# Build from the workspace root: docker build -f apps/web/Dockerfile .
FROM python:3.10-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /bin/uv
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# Dependencies first so they cache independently of app source changes.
COPY pyproject.toml uv.lock .python-version ./
COPY packages/model/pyproject.toml packages/model/
COPY apps/web/pyproject.toml apps/web/
COPY apps/sync/pyproject.toml apps/sync/
COPY apps/nq/pyproject.toml apps/nq/
RUN uv sync --frozen --no-dev --no-install-workspace --package freezing-web --extra runtime

COPY packages/model packages/model
COPY apps/web apps/web
RUN uv sync --frozen --no-dev --no-editable --package freezing-web --extra runtime

FROM python:3.10-slim
RUN addgroup --system freezing && adduser --system --ingroup freezing freezing
COPY --from=build /app/.venv /app/.venv
COPY apps/web/alembic.ini /app/alembic.ini
COPY apps/web/leaderboards /data/leaderboards
ENV PATH="/app/.venv/bin:$PATH" LEADERBOARDS_DIR=/data/leaderboards
WORKDIR /app
USER freezing
EXPOSE 8000
ENTRYPOINT ["gunicorn", "--bind", "0.0.0.0:8000", "freezing.web:app"]
