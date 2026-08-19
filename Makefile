.PHONY: all lint test lint-signer lint-repo lint-actions test-signer test-repo test-e2e

all: lint test

lint: lint-signer lint-repo lint-actions

test: test-signer test-repo test-e2e

ENV = UV_PROJECT_ENVIRONMENT=.venvs/$@ uv

lint-signer:
	$(ENV) sync --package tuf-on-ci-sign --group dev --frozen
	$(ENV) run --no-sync ruff check signer
	$(ENV) run --no-sync ruff format --check --diff --quiet signer
	$(ENV) run --no-sync mypy signer

lint-repo:
	$(ENV) sync --package tuf-on-ci --group dev --frozen
	$(ENV) run --no-sync ruff check repo
	$(ENV) run --no-sync ruff format --check --diff --quiet repo
	$(ENV) run --no-sync mypy repo

lint-actions:
	$(ENV) sync --only-group dev --frozen
	$(ENV) run --no-sync zizmor --quiet .

test-signer:
	$(ENV) sync --package tuf-on-ci-sign --frozen --no-dev
	$(ENV) run --no-sync --directory signer python -m unittest

test-repo:
	$(ENV) sync --package tuf-on-ci --frozen --no-dev
	$(ENV) run --no-sync --directory repo python -m unittest

test-e2e:
	$(ENV) sync --frozen --no-dev
	$(ENV) run --no-sync --directory tests ./e2e.sh

