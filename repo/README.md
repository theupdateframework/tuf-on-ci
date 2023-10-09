## CI tools for TUF-on-CI

These commands are used by the GitHub actions in the [actions directory](../actions/). There should be no reason to install or use them elsewhere (except for debugging and testing).

### Installation

Development install: `pip install -e .`

### Usage

`tuf-on-ci-status [--push]`: Prints status of the signing event (aka current branch) based on the changes done in the signing event compared to the starting point of the event. Creates commits in the signing event branch, making the artifact hashes match current artifacts.  If `--push` is used, the changes are pushed to signing event branch. Returns 0 if the signing event changes are correctly signed.

`tuf-on-ci-online-sign [--push]`: Updates snapshot & timestamp based on current repository content. If `--push` is used, the changes are pushed to main branch.

`tuf-on-ci-build-repository --metadata METADATA_DIR [--artifacts ARTIFACT_DIR]`: Creates a publishable versions of metadata and artifacts in given directories.

`tuf-on-ci-create-signing-events [--push]`: Creates version bump commits for offline signed roles that are close to expiry. If `--push` is used, the changes are pushed to signing event branches (branch per role): the signing event names are printed on stdout.
