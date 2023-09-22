# Online Signing in TUF-on-CI

When a TUF-on-CI repository is initialized, an online signing method is chosen. This
choice can be changed later. The chosen method will be used by the repository to sign
`timestamp` and `snapshot` roles automatically.

Currently supported signing methods include
* Sigstore (experimental)
* Google Cloud KMS
* Azure Key Vault

## Configuration

### Sigstore

Using sigstore as the online signing method requires no configuration but is
currently experimental (and not supported by all TUF client libraries)

### Google Cloud KMS

1. Make sure Google Cloud Workload Identity Federation allows your Github repositorys OIDC identity to sign
   with a KMS key.
1. Define your authentication details as repository variables in _Settings->Secrets and variables->Actions->Variables_:
   ```
   GCP_WORKLOAD_IDENTITY_PROVIDER: projects/843741030650/locations/global/workloadIdentityPools/git-repo-demo/providers/git-repo-demo
   GCP_SERVICE_ACCOUNT: git-repo-demo@python-tuf-kms.iam.gserviceaccount.com
   ```
1. _(only needed for initial configuration)_ Prepare your local environment for accessing the cloud KMS:
   Use [gcloud](https://cloud.google.com/sdk/docs/install) and authenticate in the
   environment where you plan to run `tuf-on-ci-delegate` tool (you will need
   _roles/cloudkms.publicKeyViewer_ permission on KMS)

### Azure Key Vault

1. Make sure Azure allows this repository OIDC identity to sign with a Key Vault key.
1. Define `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` and `AZURE_SUBSCRIPTION_ID` as repository
   secrets in _Settings->Secrets and variables->Actions->Secrets_
1. Modify the online-sign workflow like this:
    ```yaml
    jobs:
        online-sign:
        runs-on: ubuntu-latest

        permissions:
            id-token: 'write' # for OIDC identity access
            contents: 'write' # for committing snapshot/timestamp changes
            actions: 'write' # for dispatching publish workflow

        steps:
        ...
            - name: Login to Azure
              uses: azure/login@v1
              with:
                client-id: ${{ secrets.AZURE_CLIENT_ID }}
                tenant-id: ${{ secrets.AZURE_TENANT_ID }}
                subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
        ...
            - id: online-sign
              uses: theupdateframework/tuf-on-ci/actions/online-sign@main
    ```
1. _(only needed for initial configuration)_ Prepare your local environment: Use [az
       login](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli)
       and authenticate against the environment where the key vault
       exists. You will need to the role _"Key Vault Crypto User"_).
