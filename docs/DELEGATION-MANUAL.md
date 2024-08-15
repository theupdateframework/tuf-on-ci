# TUF-on-CI Online Delegations Manual

> [!WARNING]
> This functionality is still experimental. Changes in the API and
> behaviour may happen in future releases.

TUF-on-CI now supports "online" delegations, which refers to a
delegator using an "online" key, such as a cloud KMS.

The difference is that now there is an action that can be called to
have TUF-on-CI automatically sign updated metadata files.

The option to use an online signer is given when a role is
modified. When configuring a role the cli now provides this choice:

```
Enter name of role to modify: targets
Modifying delegation for targets

Configuring role targets
 1. Configure signers: [@-test-user-1], requiring 1 signatures
 2. Configure expiry: Role expires in 365 days, re-signing starts 60 days before expiry
Please choose an option or press enter to continue: 1
Choose what keytype to use:
1. Configure offline signers:
2. Configure online signers
```

If online signers is selected, configuration similar to when
configuring the online role (snapshot and timestamp) is required.

## Limitations

This feature is still experimental, and also there are some known issues

* **Dispatching of delegation workflows**: Due to GitHub's limitation
  on GitHub Action invocation based on changes made by the default
  GitHub Action token, automated signing may be required to be
  dispatched manually.

  A solution to this can be to use a different token, such as a PAT or
  an OAuth application.

* **Number of signers**: Currently only a single online signer can be
  configured for a delegation. This also means that there can not be a
  combination of offline and online signers. As online keys are mostly
  used for automated signing, this limitation should not impose any
  practical problems.

## Use cases

This could be used when a deployment wants to programatically add
content (targets) to a TUF repository, and rely on automated
signing. The operator of the repository would still need to provide
some custom automation, such as how to modify the repository and push
the changes, how to approve pull requests and so on.

## Operation

To automate signing, the primary API is the [online sign targets
action](actions/online-sign-targets/action.yml). In the default
configuration, this action is not used and so must explicitly be
called.

The preferred method is to create a GitHub Actions job that is run
when one or more metadata files for delegations are modified. This
example shows how changes to `foo-delegation` can be signed
automatically. This Example uses Azure KMS, but GCP and AWS KMSes are
also supported.

```yml
name: Foo Delegate Signing

permissions: {}

on:
  workflow_dispatch:
  push:
    branches: ['sign/**']
    paths:
      - metadata/foo-delegate.json
jobs:
  sign-and-push:
    name: TUF-on-CI Foo Delegate sign
    runs-on: ubuntu-latest
    permissions:
      contents: write # for making commits in signing event and for modifying draft state
      pull-requests: write # for modifying signing event pull requests
      actions: write # for dispatching another signing-event workflow
    steps:

      - name: Sign delegation
        uses: theupdateframework/tuf-on-ci/actions/online-sign-targets@main
        with:
          azure_client_id: secrets.AZURE_CLIENT_ID
          azure_tenant_id: secrets.AZURE_TENANT_ID
          azure_subscription_id: secrets.AZURE_SUBSCRIPTION_ID
          targets_to_sign: foo-delegate
          token: ${{ secrets.TUF_ON_CI_TOKEN || secrets.GITHUB_TOKEN }}
```

The steps to work with automated delegation signing would thus be:

1. A signing event ( e.g. `sign/update-foo-target`) branch is created
   and pushed
1. TUF-on-CI creates a signing event PR
1. TUF-on-CI detects changed targets and updates delegation metadata
   and commits the changes
1. Automated signing detects changes to delegation metadata and signs
   it, and commits the changes
1. TUF-on-CI moves signing event PR from draft to ready for review

The PR can then be reviewed as normal and merged when ready as for any
signing event.
