# Freezing Saddles

Monorepo for the [Freezing Saddles](https://freezingsaddles.org) winter cycling
competition. It replaces the separate `freezing-model`, `freezing-web`,
`freezing-sync`, `freezing-nq`, `freezing-beanstalkd` and `freezing-compose`
repositories, whose histories are preserved here.

| Path | What it is |
| --- | --- |
| `packages/model` | shared SQLAlchemy models, migrations and message schemas |
| `apps/web` | the Flask website |
| `apps/sync` | Strava activity, athlete and weather sync worker |
| `apps/nq` | Strava webhook receiver that enqueues work for sync |
| `docker/beanstalkd` | the beanstalkd queue image |
| `deploy` | docker compose files and server scripts |

## Developing

The Python projects form a [uv](https://docs.astral.sh/uv/) workspace with a
single lock file. `freezing-model` is a workspace dependency of each app, so a
change to the model and the code that uses it land in one pull request; there
is no separate model release.

    uv sync --all-packages --all-extras   # one virtualenv for everything
    uv run black --check .                 # formatting, isort and flake8 the same way
    cd apps/sync && APP_SETTINGS=example.cfg uv run pytest -m "not live"
    cd apps/nq && uv run pytest

Each app has its own `README.md` with runtime configuration details.

Dependency versions are pinned by `uv.lock`; the apps declare compatible
ranges, the model declares the ranges it supports, and dependabot updates the
lock. Dev tools are pinned in the root `pyproject.toml` dev group.

## Building images

Every image is built from the repository root so it can see `packages/model`:

    docker build -f apps/web/Dockerfile .
    docker build -f apps/sync/Dockerfile .
    docker build -f apps/nq/Dockerfile .

Image names are unchanged: `freezingsaddles/freezing-web`, `-sync` and `-nq`.

## CI

Pull requests run lint, tests, a Bandit scan and a build of all three images
without pushing.

A push to `main` builds the images for whichever apps changed (a change under
`packages/` or to the lock file rebuilds all three), pushes them to Docker Hub
and runs the deploy job in the `production` environment. Until the cut-over the
images are tagged `main` rather than `latest`, and the `docker compose` lines
in the deploy script are commented out, so production still deploys from the
individual repositories. Cutting over means changing the tag to `latest` and
uncommenting those lines in `.github/workflows/deploy.yml`.
