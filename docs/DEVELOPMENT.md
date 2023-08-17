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

### Trying thing sout without pushing changes to remote

tuf-on-ci-sign and tuf-on-ci-delegate can be run with `--no-push` to prevent the push to
the remote signing event branch: instead a local branch of the same name will be created
(note that you are responsible for that being possible). This branch can be pushed
manually after inspection and it will work as if the push was done by the tool itself.

### Debugging repository tools

The same tool (`tuf-on-ci-status`) that runs during the automation
can be run locally too to inspect the current status of the signing
event branch.

To install the repository tools, run pip install from the
`repo/` directory where the
[pyproject.toml](repo/pyproject.toml) file exists:

```shell
$ pip install -e .
```

As an example, this would be the output when an open invitation exists
for a new user to become a root key holder:

```shell
$ tuf-on-ci-status
### Current signing event state
Event [sign/add-fakeuser-1](../compare/sign/add-fakeuser-1)
#### :x: root
root delegations have open invites (@-fakeuser-2).
Invitees can accept the invitations by running `tuf-on-ci-sign add-fakeuser-2`
$
```
