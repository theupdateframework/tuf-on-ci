.PHONY: export-constraints tox lint test test-e2e lint-signer lint-repo test-signer test-repo

all: lint test

lint: lint-signer lint-repo

lint-signer:
	tox -e lint-signer

lint-repo: action-constraints.txt
	tox -e lint-repo

test: test-signer test-repo test-e2e

test-signer:
	tox -e test-signer

test-repo: action-constraints.txt
	tox -e test-repo

test-e2e: action-constraints.txt
	tox -e test-e2e

action-constraints.txt: uv.lock
	cd repo && uv export --quiet --no-emit-workspace --no-hashes -o ../action-constraints.txt
