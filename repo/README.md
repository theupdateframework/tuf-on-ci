## CI tools for TUF-on-CI

These commands are used by the GitHub actions in the [actions directory](../actions/). There should be no reason to install or use them elsewhere (except for debugging and testing).

### Installation

Development install: `pip install -e .`

### Usage

`tuf-on-ci-status`: Prints status of the signing event (aka current branch) based on the changes done in the signing event (compared to the starting point of the event) and invites in .signing-event-state file

`tuf-on-ci-snapshot [--push] [<PUBLISH_DIR>]`: Updates snapshot & timestamp based on current repository content. If `--push` is used, the changes are pushed to main branch. If PUBLISH_DIR is given, will create a publishable repository version in PUBLISH_DIR. 

`tuf-on-ci-bump-online [--push] [<PUBLISH_DIR>]`: Bumps the online roles version if they are about to expire, and signs the changes. If `--push` is used, the changes are pushed to main branch. If PUBLISH_DIR is given, will create a publishable repository version in PUBLISH_DIR. 

`tuf-on-ci-bump-offline [--push]`: Bumps the roles versions if they are about to expire. If `--push` is used, the changes are pushed to signing event branches (branch per role): the signing event names are printed on stdout.
