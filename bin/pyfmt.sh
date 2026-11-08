#!/usr/bin/env bash
#
# Reformat the tree, then run every check the Lint workflow runs, so that a
# commit does not have to wait for CI to learn it is not clean.
#
# The reformatters change files in place; the checks only report. Anything the
# checks find is named at the end, and the script exits non-zero.

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1
ROOT=$PWD

# A virtualenv left over from another checkout makes uv warn on every command.
unset VIRTUAL_ENV

# Workspace members, for the tools that look at one package at a time.
MEMBERS="packages/model packages/common apps/web apps/sync apps/nq"
TEMPLATES="apps/web/freezing/web/templates"

failed=""

heading() { printf '\n\033[1m%s\033[0m\n' "$*"; }

# Once, up front. Every tool then runs with --no-sync, as the workflow does:
# left to sync themselves, the ones that run inside a member reinstall that
# member on every invocation.
heading "uv sync"
uv sync --all-packages --all-extras || exit 1

# run <name> <command...> -- announces it, and remembers if it complained.
run() {
    name=$1
    shift
    heading "$name"
    "$@" || failed="$failed $name"
}

# Porcelain alone says only which files are dirty, not what is in them, so a
# file that was already modified and is then reformatted would look unchanged.
snapshot() { git status --porcelain; git diff HEAD; }

before=$(snapshot)

# These fix what they find.
run black uv run --no-sync black .
run isort uv run --no-sync isort .
run "djlint --reformat" uv run --no-sync djlint --reformat "$TEMPLATES"
run "pymarkdown fix" uv run --no-sync pymarkdown fix apps/web

# These only report, which is the point of running them here.
run flake8 uv run --no-sync flake8 .
run mypy uv run --no-sync mypy
run djlint uv run --no-sync djlint "$TEMPLATES"
run pymarkdown uv run --no-sync pymarkdown scan apps/web

# fawltydeps reads one member's imports against one member's dependencies, so
# it runs in each, pointed at the environment they all share.
for member in $MEMBERS; do
    heading "fawltydeps $member"
    (cd "$member" && uv run --no-sync fawltydeps --pyenv "$ROOT/.venv") ||
        failed="$failed fawltydeps($member)"
done

if [ "$before" != "$(snapshot)" ]; then
    heading "Reformatted -- look these over before committing"
    git status --short
fi

if [ -n "$failed" ]; then
    heading "Not clean:$failed"
    exit 1
fi

heading "Clean"
