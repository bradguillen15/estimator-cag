#!/usr/bin/env bash
# API checks. Single source of truth: CI (`api-tests`) and the pre-commit hook both run this file.
set -euo pipefail
cd "$(dirname "$0")/../.."

uv sync --locked   # fails if uv.lock is out of date with pyproject.toml
# CI sets CI_COVERAGE=1 to also write an lcov report for Coveralls; the pre-commit hook skips it.
if [[ -n "${CI_COVERAGE:-}" ]]; then
  uv run pytest --cov=app --cov-report=term --cov-report=lcov:coverage/api.lcov
else
  uv run pytest
fi
