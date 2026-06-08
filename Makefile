TOX = uv run --frozen --only-group dev tox --quiet

.PHONY: lint test lint-signer lint-repo lint-actions test-signer test-repo test-e2e

all: lint test

lint: lint-signer lint-repo lint-actions

test: test-signer test-repo test-e2e

lint-signer lint-repo lint-actions test-signer test-repo test-e2e:
	$(TOX) -e $@
