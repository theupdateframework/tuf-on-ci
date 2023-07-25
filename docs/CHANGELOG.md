# Changelog

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
