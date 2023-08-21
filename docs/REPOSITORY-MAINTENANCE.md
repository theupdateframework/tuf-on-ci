# TUF-on-CI Repository Maintenance Manual

This page documents the initial setup of a TUF-on-CI repository as well as the
ongoing maintenance.

## New Repository Setup

1. Fork the [template](https://github.com/theupdateframework/tuf-on-ci-template).
1. To enable repository publishing, set _Settings->Pages->Source_ to `Github Actions`
1. Clone the repository locally and [configure your local signing tool](SIGNER-SETUP.md)
1. Choose your online signing method and [configure it](ONLINE-SIGNING-SETUP.md):
   * Google Cloud KMS and Azure Key Vault are fully supported 
   * Sigstore requires no configuration (but is experimental)
1. Run `tuf-on-ci-delegate sign/init` to configure the repository and to start the
   first signing event
   * The tool prompts for various repository details and finally prompts to 
     sign and push the initial metadata to a signing event branch
1. When this initial signing event branch is merged, the repository generates the
   first snapshot and timestamp, and publishes the first repository version

## Modifying roles and creating new ones

Modifying a role is needed when:
* A new delegated role is created
* A new signer is invited to a role
* A signer is removed from a role
* The required threshold of signatures is changed

Roles are modified with `tuf-on-ci-delegate <event> <role>`.
* The event name can be chosen freely (and will be used as a branch name). If the signing
  event does not exist yet, it will be created as a result. 
* The tool will prompt for new signers and other details, and then prompt to push changes
  to the repository.
* The push triggers creation of a signing event GitHub issue. The repository will report the
  status of the signing event and will notify signers with advice.

### Examples

TODO: Example: Creating a new delegated role

TODO: Example: Removing a signer

<details>
<summary>Example: Inviting a new root signer</summary>
In this example the root signers list contains a single signer, but it is modified to contain
two signers instead. The process is:

* tuf-on-ci-delegate is used to modify signers
* the new signer accepts the invitation and adds their keys to the delegating role's metadata
* the signers of the delegating role must accept the new key by signing the new
  version of delegating metadata

```shell
$ tuf-on-ci-delegate sign/add-fakeuser-2 root

Remote branch not found: branching off from main
Modifying delegation for root

Configuring role root
1. Configure signers: [@-fakeuser-1], requiring 1 signatures
2. Configure expiry: Role expires in 365 days, re-signing starts 60 days before expiry
Please choose an option or press enter to continue: 1
Please enter list of root signers [@-fakeuser-1]: @-fakeuser-1,@-fakeuser-2
Please enter root threshold [1]:
1. Configure signers: [@-fakeuser-1, @-fakeuser-2], requiring 1 signatures
2. Configure expiry: Role expires in 365 days, re-signing starts 60 days before expiry
Please choose an option or press enter to continue:
...
```

Once finished the changes are pushed to the signing event branch
which in the above example is `sign/add-fakueuser-2`.

The repository automation runs the [signing
automation](https://github.com/theupdateframework/tuf-on-ci-template/blob/main/.github/workflows/signing-event.yml)
that creates issues with the current signing state and tags each
signer on what's expected to do. This always provides a clear state of
the situation.

To accept the invitation and become a signer, the invitee runs
`tuf-on-ci-sign <event-name>` and provides information on what key to
use.

After this the delegating role signers (in this case root signers) accept
the new key by signing the delegating metadata version.
</details>
