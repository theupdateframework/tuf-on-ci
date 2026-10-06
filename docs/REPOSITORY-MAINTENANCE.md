# TUF-on-CI Repository Maintenance Manual

This page documents the initial setup of a TUF-on-CI repository as well as the
ongoing maintenance.

## New Repository Setup

### Setup decisions

Before initializing the repository, decide on two configuration choices (both can also be
changed later):
* **Online signing method**: Automated signing of `timestamp` and `snapshot` roles supports
  Google Cloud KMS, Azure Key Vault, AWS KMS, and Sigstore (experimental). See
  [ONLINE-SIGNING-SETUP.md](ONLINE-SIGNING-SETUP.md) for details.
* **GitHub workflow authentication**: Workflows use the default `GITHUB_TOKEN` out of the
  box, or can use a **GitHub App** to allow stricter repository security settings (such as
  branch protection on `main` and disabling pull request creation for `GITHUB_TOKEN`)
  without maintaining long-lived Personal Access Tokens. See
  [GITHUB-APP-SETUP.md](GITHUB-APP-SETUP.md) for details.

### Setup steps

1. [Create new repository](https://github.com/new?template_name=tuf-on-ci-template&template_owner=theupdateframework)
   using the tuf-on-ci template: the created repository contains all the required workflows.
1. Configure the new repository:
   * set _Settings->Pages->Source_ to `GitHub Actions`
   * Change _Settings->Environments->github-pages_ deployment branch from `main` to
     `publish`
   * Either [configure a GitHub App](GITHUB-APP-SETUP.md) or check
     _Settings->Actions->General->Allow GitHub Actions to create and approve pull requests_
     (to use the default `GITHUB_TOKEN`)
1. Clone the repository locally and [configure your local signing tool](SIGNER-SETUP.md)
1. [Configure your chosen online signing method](ONLINE-SIGNING-SETUP.md)
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
* The push triggers creation of a signing event pull request. The repository will report the
  status of the signing event in the pull request and will notify signers there.

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
that creates PRs with comments documenting current signing event state
and tags each signer. These comments (along with the PR commits) should
provide signers with a clear view of what is happening in the signing
event.

To accept the invitation and become a signer, the invitee runs
`tuf-on-ci-sign <event-name>` and provides information on what key to
use.

After this the delegating role signers (in this case root signers) accept
the new key by signing the delegating metadata version.
</details>

## Configuration and modifying workflows

tuf-on-ci workflows (with the exception of `publish`) are written in a way to minimize
need to modify the workflows: It may be useful to consider the workflows part of the
tuf-on-ci application. The intention with this is to make workflow upgrades easier:
tuf-on-ci release notes will mention when workflows change and typically the suggested
upgrade mechanism is to copy the modified workflows from tuf-on-ci-template.

Supported ways to configure and modify tuf-on-ci workflows:
* online signing is configured using signing method specific _Repository Variables_,
  see [ONLINE-SIGNING-SETUP.md](ONLINE-SIGNING-SETUP.md) for details
* A GitHub App can be optionally configured with _Repository Variable_
  `TUF_ON_CI_APP_ID` and _Repository Secret_ `TUF_ON_CI_APP_PRIVATE_KEY`, see
  [GITHUB-APP-SETUP.md](GITHUB-APP-SETUP.md) for details
* Workflow failure messages can be configured with `.github/TUF_ON_CI_TEMPLATE/failure.md`:
  Contents of this file will be included in issues that are opened if workflows fail. This is
  useful to e.g. notify the maintenance team with individual `@username` mentions (note that
  `@org/team` mentions are not supported because failure issues are opened using the default
  `GITHUB_TOKEN`).
* Signing pull request templates can be configured with
  `.github/PULL_REQUEST_TEMPLATE/signing_event.md`. Contents of this file will be included in
  the pull request message when non-maintainer signers contribute to signing events. This is
  useful to e.g. notify the maintenance team with @-mentions.
* The `publish` workflow can be customized to publish to a destination that is not
  the default GitHub Pages
