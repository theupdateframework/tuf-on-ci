# TUF-on-CI: A TUF repository and signing tool implementation

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
* Automated online signing (Google Cloud, Azure, Sigstore)
* No custom code required

The optimal use case is TUF repositories with a low to moderate frequency of change, both for artifacts and keys.

## Documentation

* [Signer Manual](docs/SIGNER-MANUAL.md)
* [Repository Maintenance Manual](docs/REPOSITORY-MAINTENANCE.md)
* [Developer notes](docs/DEVELOPMENT.md)

## Contact

* We're on [Slack](https://cloud-native.slack.com/archives/C04SHK2DPK9)
* Feel free to file issues if anything is unclear: this is a new project so docs are still lacking
* Email sent to jkukkonen at google.com will be read eventually
