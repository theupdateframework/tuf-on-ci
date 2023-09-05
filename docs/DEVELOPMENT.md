## Developer notes

A development install can be made in any environment but venv is recommended:

```shell
# Clone the project
git clone https://github.com/theupdateframework/tuf-on-ci.git
cd tuf-on-ci
# Create virtual environment
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

### Trying things out without pushing changes to remote

`tuf-on-ci-sign` and `tuf-on-ci-delegate` can be run with `--no-push` to prevent the push to
the remote signing event branch: instead a local branch of the same name will be created
(note that you are responsible for that being possible). This branch can be pushed
manually after inspection and it will work as if the push was done by the tool itself.

### Debugging repository tools

The same tool (`tuf-on-ci-status`) that runs during the signing event automation
can be run locally to inspect the current status of the signing event branch. Note
that the repository tools only operate on current commit (unlike the signing tools 
that always checkout the remote branch) 

As an example, this would be the markdown output when an open invitation exists
for a new user to become a root key holder:

```shell
$ git fetch && git checkout sign/add-fakeuser
...
$ tuf-on-ci-status
### Current signing event state
Event [sign/add-fakeuser](../compare/sign/add-fakeuser)
#### :x: root
root delegations have open invites (@-fakeuser).
Invitees can accept the invitations by running `tuf-on-ci-sign sign/add-fakeuser`
$
```
