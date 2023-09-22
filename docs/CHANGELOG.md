# Changelog

## Unreleased

NOTE: This is a major API break, users should **not** just upgrade the action versions but
repalce their workflows with newworkflows from tuf-on-ci-template.

Release contains:
* Major refactoring of actions: New actions are more logical and enable separating
  publishing fron online signing. The repository now contains a new branch "publish"
  that always points to the newest publishable repository version
* Bug fixes

Upgrade instructions:
* Remove your existing tuf-on-ci workflows and replace them with the ones
  from current tuf-on-ci-template.
* In _Settings->Environments->github-pages_ change deployment branch from `main` to
  `publish`
* If you use the experimental sigstore online signing: After updating run
  `tuf-on-ci-delegate sign/update-online-key timestamp` re-select sigstore as the signing
  system: This creates a new signing event that is required for online signing to work.

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
