#!/usr/bin/env bash
# Web checks. Single source of truth: CI (`web-tests`) and the pre-commit hook both run this file.
# Dependencies must already be installed (CI: `pnpm install --frozen-lockfile`; locally: `pnpm install`).
set -euo pipefail
cd "$(dirname "$0")/../.."

pnpm lint
# CI sets CI_COVERAGE=1 to also write web/coverage/lcov.info for Coveralls; the pre-commit hook skips it.
if [[ -n "${CI_COVERAGE:-}" ]]; then
  pnpm --filter estimator-web test:coverage
else
  pnpm test:web
fi
pnpm build   # tsc -b type-checks the app and the tests before bundling
