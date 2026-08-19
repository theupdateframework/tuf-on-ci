.PHONY: all lint test lint-signer lint-repo lint-actions test-signer test-repo test-e2e

all: lint test

lint: lint-signer lint-repo lint-actions

test: test-signer test-repo test-e2e

lint-signer:
	UV_PROJECT_ENVIRONMENT=.venv/lint-signer uv sync --package tuf-on-ci-sign --frozen
	UV_PROJECT_ENVIRONMENT=.venv/lint-signer uv run ruff check signer
	UV_PROJECT_ENVIRONMENT=.venv/lint-signer uv run ruff format --check --diff --quiet signer
	UV_PROJECT_ENVIRONMENT=.venv/lint-signer uv run mypy signer

lint-repo:
	UV_PROJECT_ENVIRONMENT=.venv/lint-repo uv sync --package tuf-on-ci --frozen
	UV_PROJECT_ENVIRONMENT=.venv/lint-repo uv run ruff check repo
	UV_PROJECT_ENVIRONMENT=.venv/lint-repo uv run ruff format --check --diff --quiet repo
	UV_PROJECT_ENVIRONMENT=.venv/lint-repo uv run mypy repo

lint-actions:
	UV_PROJECT_ENVIRONMENT=.venv/lint-actions uv sync --only-group dev --frozen
	UV_PROJECT_ENVIRONMENT=.venv/lint-actions uv run zizmor --quiet .

test-signer:
	UV_PROJECT_ENVIRONMENT=.venv/test-signer uv sync --package tuf-on-ci-sign --frozen --no-dev
	UV_PROJECT_ENVIRONMENT=.venv/test-signer uv run --directory signer python -m unittest

test-repo:
	UV_PROJECT_ENVIRONMENT=.venv/test-repo uv sync --package tuf-on-ci --frozen --no-dev
	UV_PROJECT_ENVIRONMENT=.venv/test-repo uv run --directory repo python -m unittest

test-e2e:
	UV_PROJECT_ENVIRONMENT=.venv/test-e2e uv sync --frozen --no-dev
	UV_PROJECT_ENVIRONMENT=.venv/test-e2e uv run --directory tests ./e2e.sh

