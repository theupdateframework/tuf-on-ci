# Changelog

## Unreleased

## v0.10.0

Release includes several new features. It also fixes an issue with TUF keyids,
see issue #292 (note that existing keyids are not automatically made compliant:
`tuf-on-ci-delegate --force-compliant-keyids` can be used in a signing event to
make that happen).

GitHub workflows require no changes (but you may want to add a
`.github/TUF_ON_CI_TEMPLATE/failure.md` file, see below).

**Changes**

* Artifact directories can now be up to 5 levels deep (#238)
* actions: All action requirements are now version pinned (#248)
* actions: `.github/TUF_ON_CI_TEMPLATE/failure.md` can now be used to
  define custom content for workflow failure issues (#270)
* `build-repository` action: A human readable repository description
  is generated in index.html in the published metadata dir (#313)

**Fixes**

* signer: keyid generation was fixed to be specification compliant (#294)
  * A feature was added to fix noncompliant keyids in repositories
    where they non-compliant keyids already present (#338)
* `test-repository` action: Use a better default artifact-url (#275),
  handle a initial root in more cases (#346)
* `build-repository` action: Delegation tree is now used to decide which
  metadata to include in published repo (#344)
* tuf minimum dependency is now correctly set to 3.1 (#329)

## v0.9.0

GitHub Actions users are adviced to upgrade for safer dependency
pinning that should avoid breakage in future.

**Changes**

* actions: test-repository action has many additional features (#239)
* actions: python package versions are now in logs again (#247)
* signer: Improve signing robustness (#237)
* Dependency updates (including more strictly pinned securesystemslib)

**GitHub Actions upgrade instructions**

A plain version bump from 0.8 works: Workflows require no changes.

## v0.8.0

**Changes**

* Signer now opens PRs in a browser automatically when in
  non-maintainer signing flow
* Signer now has runtime version checking: A message is printed out
  if a new version is available
* Actions have dependency updates

**GitHub Actions upgrade instructions**

A plain version bump from 0.7 works: Workflows require no changes.

## v0.7.0

**Changes**

* Signer has improved signing error handling
* Custom fields in TargetFile metadata are now preserved during target update
  (this is a workaround mostly for sigstore root-signing legacy artifacts)

**Upgrade instructions**

A plain version bump from 0.6 works: Workflows require no changes.

## v0.6.0

**NOTE:** please see upgrade instructions below.

**Changes**

* Signing events now happen in GitHub pull requests
* Signer now probes for PKCS11 module: configuring that is no longer
  required, as long as as the module is in one of the expected locations.

**Upgrade instructions**

* As usual we recommend copying your workflows from
  https://github.com/theupdateframework/tuf-on-ci-template/.
  * signing event action no longer needs `issues: write` permission
    but instead requires `pull-requests: write`
* Custom token users need to create a new token with an additional
  permission `Pull requests: write`
* _Settings->Actions->General->Allow GitHub Actions to create and
  approve pull requests_ needs to be enabled in repository settings
  (not required if a custom token is used)

## v0.5.0

**NOTE:** Do not accept a dependabot upgrade, please see upgrade
instructions.

This release contains improved failure handling and testing.

**Changes**

* New action test-repository: This new action enables smoke testing
  every published repository with a TUF client.
* New action update-issue: This action enables automated filing of
  issues when a TUF-on-CI workflow fails

**Upgrade instructions**

As usual we recommend copying your workflows from
https://github.com/theupdateframework/tuf-on-ci-template/ as there
are a number of changes, including a new reusable workflow.

## v0.4.0

NOTE: This is a major Actions API break, users should **not** just upgrade the action
versions but should instead update their workflows based on the ones from
tuf-on-ci-template.

Changes
* Support for custom GitHub tokens: see [REPOSITORY-MAINTENANCE.md].
* Uses upload-artifact v4: this means publish workflow must use
  download-artifact v4
* All commits are now done with "Signed-Off-By"

Upgrade instructions from v0.3.0:
* We recommend using the workflows from tuf-on-ci-template (or to merge changes from
  there if you have loal changes) to ensure workflows stay compatible with the
  tuf-on-ci actions

## v0.3.0

NOTE: This is a major API break, users should **not** just upgrade the action versions but
should replace their `publish.yml` workflow with the new workflow from tuf-on-ci-template.

Release contains:
* New KMS support: AWS KMS (#120)
* Bugix: When publish after online signing, in very rare conditions
  the wrong version could be published due to a race condition (#127)

Upgrade instructions from v0.2.0:
* When the Dependabot PR is created, update the PR to include the
  updated `publish.yml` from `tuf-on-ci-template` repository. Then the
  PR can be approved and merged without breaking any workflows.

Thanks to Jonny Stoten, a new contributor

## v0.2.0

* GitHub actions now output step summaries: these are visible in workflow
  run pages on Github (#96)
* Improved output in signing event status comments (#101)
* Fixed online signing with ambient Sigstore identity, which broke in 0.1.0
  (#118)

Upgrade instructions from v0.1.0:
 * Dependabot version bump can be accepted as is

## v0.1.0

NOTE: This is a major API break, users should **not** just upgrade the action versions but
should replace their workflows with new workflows from tuf-on-ci-template.

Release contains:
* Major refactoring of actions: New actions are more logical and enable separating
  publishing fron online signing. The repository now contains a new branch "publish"
  that always points to the newest publishable repository version
* Improved Sigstore signer registration flow
* Bug fixes

Upgrade instructions:
* Remove your existing tuf-on-ci workflows and replace them with the ones
  from current tuf-on-ci-template.
* In _Settings->Environments->github-pages_ change deployment branch from `main` to
  `publish`
* If you use the experimental sigstore online signing: After updating run
  `tuf-on-ci-delegate sign/update-online-key timestamp` re-select sigstore as the signing
  system: This creates a new signing event that is required for online signing to work.

Thanks to contributors Radoslav Dimitrov, Meredith Lancaster and lv291.

## v0.0.1

initial release of TUF-on-CI.

TUF-on-CI is a repository and signer implementation of
https://theupdateframework.io/ that runs on a Continuous Integration platform.
Features include:
* Threshold signing with hardware keys and Sigstore
* Automated online signing with multiple KMSs
* Polished signing user experience
* No custom code required


The signer is *not* available from PyPI in this release but will be in future releases.
See [README.md](../README.md) for repository and signer setup instructions.

### Upgrading an existing repository installation

* Start pinning tuf-on-ci actions in your workflows (see example in https://github.com/theupdateframework/tuf-on-ci-template/pull/3)
* Use Dependabot in your GitHub project to get automatic update PRs in the future
