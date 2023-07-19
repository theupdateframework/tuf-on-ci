# TUF-on-CI: A TUF repository and signing tool implementation

This is a TUF implementation that operates on Continuous Integration platform.
Supported features include:
* Threshold signing with offline keys, guided by CI
* Automated online signing
* Polished signer and maintainer experience
* No custom code required

The optimal use case is TUF repositories with a low to moderate frequency of change, both for target files and keys.

This is a Work-In-Progress and no stable releases have been made yet. See
[example](https://github.com/jku/test-repo-for-playground/) for an instance running TUF-on-CI.

## Documentation

* [Design document](https://docs.google.com/document/d/140jiFHGc3wwEmNaJmUdgkNeNK4i4CC-lm5-eVQYXiL0/edit?resourcekey=0-CLZhA-H2jtd3WQD-lBLsqQ)
* [Developer notes](docs/DEVELOPMENT.md)

## Setup

Current signing requirements are:
 * A HW key with PIV support (such as a newer Yubikey)
 * Python 3.11 or higher

### Setup signer

1. Create a PIV signing key on your HW key if you don't have one. For Yubikey owners the easiest tool is Yubikey manager:![Yubikey manager UI](docs/yubikey-manager.png)

   [yubico-piv-tool](https://developers.yubico.com/yubico-piv-tool/) can also do it (just copy-paste the public key and certificate when requested):
   ```shell
   yubico-piv-tool -a generate -a verify-pin -a selfsign -a import-certificate -s 9c -k -A ECCP256 -S '/CN=piv_auth/OU=example/O=example.com/'
   ```
1. Install a PKCS#11 module. TUF-on-CI has been tested with the Yubico implementation,
   Debian users can install it with
   ```shell
   $ apt install ykcs11
   ```
   macOS users can install with
   ```shell
   $ brew install yubico-piv-tool
   ```
1. install tuf-on-ci-sign
   ```shell
   $ pip install git+https://git@github.com/theupdateframework/tuf-on-ci#subdirectory=signer
   ```

### Configure signer

Whenever you run signing tools, you need a configuration file `.tuf-on-ci-sign.ini` in the root dir of the git repository that contains the metadata:
   ```
   [settings]
   # Path to PKCS#11 module
   pykcs11lib = /usr/lib/x86_64-linux-gnu/libykcs11.so
   # GitHub username
   user-name = @my-github-username

   # Git remotes to pull and push from
   pull-remote = origin
   push-remote = origin
   ```

A [provided
script](https://github.com/theupdateframework/tuf-on-ci/blob/main/signer/create-config-file.sh)
exists that can generate one.

### Setup a new TUF-on-CI repository

1. Fork the [template](https://github.com/theupdateframework/tuf-on-ci-template).
1. To enable repository publishing, set _Settings->Pages->Source_ to `Github Actions`

#### Using a KMS

Currently Azure and Google cloud KMS are supported.
If you intend to use a Cloud KMS for online signing (instead of the default
"ambient Sigstore signing"), there are a couple of extra steps:
1. Make sure Cloud KMS allows this repository OIDC identity to sign
   with a KMS key.
    1. For GCP, define your authentication details as repository
       variables in _Settings->Secrets and variables->Actions->Variables_. Examples:
       ```
       GCP_WORKLOAD_IDENTITY_PROVIDER: projects/843741030650/locations/global/workloadIdentityPools/git-repo-demo/providers/git-repo-demo
       GCP_SERVICE_ACCOUNT: git-repo-demo@python-tuf-kms.iam.gserviceaccount.com
       ```
    1. For Azure, `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` and
       `AZURE_SUBSCRIPTION_ID` must be set. Then an extra step in the
       workflow must be inserted like this:
       ```yaml
       jobs:
         snapshot:
         runs-on: ubuntu-latest

           permissions:
             id-token: 'write' # for OIDC identity access
             contents: 'write' # for committing snapshot/timestamp changes
           ...
           steps:
             - name: Login to Azure
               uses: azure/login@v1
               with:
                 client-id: ${{ secrets.AZURE_CLIENT_ID }}
                 tenant-id: ${{ secrets.AZURE_TENANT_ID }}
                 subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
             - id: snapshot
               uses: theupdateframework/tuf-on-ci/actions/snapshot@main
         ...
         deploy:

       ```
1. _(only needed for initial repository creation)_ Prepar local
   environment for accessing the cloud KMS.
    1. For GCP use [gcloud](https://cloud.google.com/sdk/docs/install)
       and authenticate in the environment where you plan to run
       tuf-on-ci-delegate tool (you will need
       _roles/cloudkms.publicKeyViewer_ permission)

    1. For Azure use [az
       login](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli)
       and authenticate against the environment where the key vault
       exists. You will need to the role _"Key Vault Crypto User"_).

## Operation

Both tools (`tuf-on-ci-delegate` and `tuf-on-ci-sign`) take one required argument, the
signing event name (it is used as a git branch name). Typically the signing event exists
and you know its name but in some cases (delegation, target modification) you can choose
a name for a new signing event: anything starting with "sign/" is fine.

The tools will fetch the current signing event content from a matching branch in
_pull-remote_. After signing or delegation changes, the tools will push the changes
to matching branch on _push-remote_.

Notes on remotes configured in `.tuf-on-ci-sign.ini`:
* _pull-remote_ should always be the actual TUF repository
* If you have permissions to push to the TUF repository, you can set _push-remote_ to same value
* Otherwise you can set _push-remote_ to your fork: in this case after running the tools, you
  should make a PR from your fork to the signing event branch on the TUF repository

### Initial signing event

1. Run delegate tool to create initial metadata
   ```shell
   $ tuf-on-ci-delegate <event-name>
   ```
1. Respond to the prompts

### Add a delegation or modify an existing one

1. Run delegate tool when you want to modify a roles delegation
   ```shell
   $ tuf-on-ci-delegate <event-name> <role>
   ```
1. Respond to the prompts

### Modify target files

Make target file changes in the signing event git branch using tools and review processes
of your choice.

```shell
$ git fetch origin
$ git switch -C sign/my-target-changes origin/main
$ echo "test content" > targets/file.txt
$ git commit -m "Add a target file" -- targets/file.txt
$ git push origin sign/my-target-changes
```

This starts a signing event (or updates an existing signing event).

### Sign changes made by others

Signing should be done when the signing event (GitHub issue) asks for it:

1. Run signer tool in the signing event branch
   ```shell
   $ tuf-on-ci-sign <event-name>
   ```
1. Respond to the prompts

## Components

### Repository template

Status: Implemented in the tuf-on-ci-template project. Workflows include
* signing-event
* snapshot
* version-bumps

See [here](https://github.com/theupdateframework/tuf-on-ci-template).

### Repository actions

Status:
* *actions/signing-event*: functionality is there but output is a work in progress, and
  various checks are still unimplemented
* *actions/snapshot*: Implemented
* *actions/online-version-bump*: Implemented
* *actions/offline-version-bump*: Implemented

Various parts are still very experimental
* loads of content safety checks are missing
* output of the signing event is a work in progress
* failures in the actions are not visible to user
* testing is still completely manual

See [repo/](repo/), See [actions/](actions/)

### signing tool

Status:
* tuf-on-ci-delegate mostly implemented
* tuf-on-ci-sign mostly implemented, although output is a work in progress

See [signer/](signer/)

### Client

`client/` contains a simple downloader client. It can securely lookup and download artifacts from the repository.
There is nothing specific to this repository implementation in the client implementation: any other client could be used.

TODO: Client is currently not up-to-date WRT repository implementation.

## Examples

### Initialize a new repository

1. Instantiate  [template](https://github.com/theupdateframework/tuf-on-ci-template)
1. Enable publishing to GitHub Pages: `Settings > Pages > Source:
   GitHub Actions`
1. Install the signer tools as described
   [here](https://github.com/theupdateframework/tuf-on-ci/blob/main/signer/README.md)
   on your local computer
1. Clone the instantiated repository
1. Prepate the configuration file (`.tuf-on-ci-sign.ini`)
1. Run `tuf-on-ci-delegate <event-name>`
1. Follow the instructions to configure the root, after this is done a
   new branch with `<event-name>` is pushed to `origin`
1. Once the new metadata is pushed, reivew the change and merge into
   `main`
1. Once merged to main snapshot and timestamp workflows will run and
   publish the root for consumption

### Adding a new signer

Adding a new root signer is done via the `tuf-on-ci-sign` command.

```shell
$ tuf-on-ci-delegate sign/add-fakeuser-2

Remote branch not found: branching off from main
Enter name of role to modify: root
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

Once finished the changes are pushed to the branch `<event-name>`
which in the above example is `sign/add-fakueuser-2`.

By naming the event with `sign/<event-name>` automation will pick up
this branch and run the [signing
automation](https://github.com/theupdateframework/tuf-on-ci-template/blob/main/.github/workflows/signing-event.yml)
that creates issues with the current signing state and tags each
signer on what's expected to do. This always provides a clear state of
the situation.

To accept the invitation and become a signer, the invitee runs
`tuf-on-ci-sign <event-name>` and provides information on what key to
use. After completion the updated metadata will be pushed to
`origin`. 

When adding or changing root signer, remember that a quorum of
_current_ key-holders **must** sign the updated root metadata for it
to be valid.

### Removing a signer

To remove a signer, follow the steps when adding a signer. When
configuring the desired role, add a new list of signers where the
desired users are not present. After this a new signing event happens
and so all kept signers must resign the metadata.

### Adding targets

Create a new branch, and give it a descriptive name, then add the
targets and push the branch to `origin`

```shell
$ git checkout -b sign/add-targets
$ mkdir targets
$ echo file1 > targets/file1.txt
$ echo file2 > targets/file2.txt
```

The branch can now be pushed to `origin` and an issue will be created
that tracks the changes and the required signaturesby the correct key
holders.

Run the `tuf-on-ci-sign <event-name>` command to sign the metadata
and push the branch to `origin`, once pushed, and signed by all key
holders create a PR and merge. The snapshot workflow will then run an
publish the repository for consumption.

## Debug tools

The same tool (`tuf-on-ci-status`) that runs during the automation
can be run locally too to inspect the current status of a branch
(signing event).

To install the repository tools, run pip install from the
`repo/` directory where the
[pyproject.toml](repo/pyproject.toml) file exists:

```shell
$ pip install -e .
```

As an example, this would be the output when an open invitation exists
for a new user to become a root key holder:

```shell
$ tuf-on-ci-status
### Current signing event state
Event [sign/add-fakeuser-1](../compare/sign/add-fakeuser-1)
#### :x: root
root delegations have open invites (@-fakeuser-2).
Invitees can accept the invitations by running `tuf-on-ci-sign add-fakeuser-2`
$
```
