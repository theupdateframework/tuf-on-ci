## Developer notes

A development install can be made in any environment but venv is recommended:

```shell
# Create environment
python3 -m venv .venv
# Enter environment
source .venv/bin/activate
# install the signing and repository tools as editable
pip install -e ./signer -e ./repo
# install tox for a reproducible testing environment
pip install tox
```

At this point `tuf-on-ci-sign` and other commands are available from the editable install (source code).

### Running tests and linters

Tests and lints can be run with tox:

```shell
# Run all lints
tox -m lint

# run all tests
tox -m test
```
