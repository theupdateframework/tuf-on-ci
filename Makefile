.PHONY: tox lint test test-e2e lint-signer lint-repo test-signer test-repo

all: lint test

lint: lint-signer lint-repo lint-actions

lint-signer:
	uv run --frozen tox -e lint-signer

lint-repo:
	uv run --frozen tox -e lint-repo

lint-actions:
	uv run --frozen tox -e lint-actions

test: test-signer test-repo test-e2e

test-signer:
	uv run --frozen tox -e test-signer

test-repo:
	uv run --frozen tox -e test-repo

test-e2e:
	uv run --frozen tox -e test-e2e
