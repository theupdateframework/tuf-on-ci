# TUF-on-CI: A TUF Repository and Signing Tool

TUF-on-CI is a secure artifact delivery system that operates on a Continuous Integration
platform. It contains a [TUF](https://theupdateframework.io) repository implementation and an
easy-to-use local signing system that supports hardware keys (e.g. Yubikeys).

TUF-on-CI can be used to publish a TUF repository that contains digitally signed metadata.
Any TUF-compatible download client can use this repository to securely download
the artifacts described in the repository.

This system is highly secure against infrastructure compromise: Even a fully compromised
repository hosting will not lead to compromised downloader clients.

Supported features include:
* Guided signing events for distributed signing
* TUF delegations with signature thresholds
* Signing with hardware keys and Sigstore
* Automated online signing (Google Cloud, Azure, AWS, Sigstore)
* No custom code required

The optimal use case is TUF repositories with a low to moderate frequency of change, both for artifacts and keys.

## Documentation

* [Signer Manual](docs/SIGNER-MANUAL.md)
* [Repository Maintenance Manual](docs/REPOSITORY-MAINTENANCE.md)
* [Developer notes](docs/DEVELOPMENT.md)

## Deployments

![logos](https://github.com/theupdateframework/tuf-on-ci/assets/31889/34eb2a5e-b9a2-41ad-b333-6a28590b17f3)

* The [Sigstore project](https://www.sigstore.dev/) uses tuf-on-ci to manage their staging TUF repository in
  [root-signing-staging](https://github.com/sigstore/root-signing-staging). This repository is
  used to deliver the Sigstore root of trust to all sigstore clients. Production TUF repository
  is likely to follow later this year
* GitHub maintains a TUF repository for their
  [Artifact Attestations](https://github.blog/2024-05-02-introducing-artifact-attestations-now-in-public-beta/)
  with tuf-on-ci
* There is also a [demo deployment](https://github.com/jku/tuf-demo/) for the TUF community

## Contact

* We're on [Slack](https://cloud-native.slack.com/archives/C04SHK2DPK9)
* Feel free to file issues if anything is unclear: this is a new project so docs are still lacking
* Email sent to jkukkonen at google.com will be read eventually
