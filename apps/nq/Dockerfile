# Build from the workspace root: docker build -f apps/nq/Dockerfile .
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
RUN uv sync --frozen --no-dev --no-install-workspace --package freezing-nq

COPY packages/model packages/model
COPY apps/nq apps/nq
RUN uv sync --frozen --no-dev --no-editable --package freezing-nq

FROM python:3.10-slim
COPY --from=build /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
WORKDIR /app
EXPOSE 8000
ENTRYPOINT ["gunicorn", "--bind", "0.0.0.0:8000", "freezing.nq.app:make_app()"]
