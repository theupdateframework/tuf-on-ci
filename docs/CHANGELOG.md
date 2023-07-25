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

The signer is available from PyPI: `pip install tuf-on-ci-sign`.
See [README.md](../README.md) for repository setup instructions.

