# GitHub App Authentication in TUF-on-CI

By default, TUF-on-CI workflows authenticate using the built-in `GITHUB_TOKEN`. While this
works out of the box, configuring a GitHub App is recommended for production repositories
to avoid long-lived Personal Access Tokens (PATs).

Using a GitHub App allows you to:
* Avoid long lived bearer tokens in repository secrets
* Enable branch protection on `main` with only GitHub App in the bypass list for periodic
  online signing commits
* Uncheck _Allow GitHub Actions to create and approve pull requests_
  so that arbitrary workflows using `GITHUB_TOKEN` cannot open or approve pull requests.

## Security model

* **Short-lived, downscoped tokens**: Instead of storing a long-lived token, workflows
  use `actions/create-github-app-token` to mint a short lived token. Each workflow
  requests only the permissions it needs on the current repository:
  * `online-sign`: `contents: write`, `actions: write`
  * `create-signing-events`: `contents: write`
  * `signing-event`: `contents: write`, `pull-requests: write`
* **Private key isolation**: The GitHub App private key (`TUF_ON_CI_APP_PRIVATE_KEY`) is
  only passed to `actions/create-github-app-token` in the caller workflow. The `tuf-on-ci`
  actions only ever see the short-lived token.
* **Workflow modification protection**: The GitHub App is blocked from modifying
  `.github/workflows/*` files, even when the App is allowed to bypass branch protection on `main`.

## Setup instructions

1. **Create the GitHub App** in your organization or personal account (_Organization Settings_
   or _Settings -> Developer settings -> GitHub Apps -> New GitHub App_):
   * **GitHub App name**: e.g. `<repo-name>-tuf-on-ci`. Visible in PR and issue comments
   * **Homepage URL**: the repository URL
   * **Callback URL, Setup URL, and OAuth options**: leave at defaults
   * **Webhook**: uncheck _Active_
   * **Repository permissions**:
     * `Actions`: _Read and write_ (to dispatch `publish.yml` after online signing)
     * `Contents`: _Read and write_ (to push online signing commits, `publish` branch updates, and signing event branches/commits)
     * `Pull requests`: _Read and write_ (to create, update, and comment on signing event pull requests)
   * **Where can this GitHub App be installed?**: _Only on this account_
1. **Generate credentials**:
   * On the App settings page, copy the **Client ID**
   * Under **Private keys**, click **Generate a private key** to download the `.pem` file.
1. **Install the GitHub App**:
   * In the App settings sidebar, select **Install App** and **Only select repositories**
     -> your TUF-on-CI repository.
1. **Configure the repository**:
   * Create a _Repository Variable_ (_Settings -> Secrets and variables -> Actions -> Variables_)
     `TUF_ON_CI_APP_ID` with the App's Client ID
   * Create a _Repository Secret_ (_Settings -> Secrets and variables -> Actions -> Secrets_)
     `TUF_ON_CI_APP_PRIVATE_KEY` with the contents of the downloaded `.pem` file.
     The local private key copy should be destroyed at this point.
1. **Tighten repository settings**:
   * Uncheck _Settings -> Actions -> General -> Allow GitHub Actions to create and approve pull requests_.
   * In _Settings -> Rules -> Rulesets_ for `main`, enable
     _Require a pull request before merging_ and add the GitHub App to the bypass list
   * Optionally, you can also remove the job `permissions:` entries marked
     `# ... (not needed if using GitHub App)` in `online-sign.yml`, `create-signing-events.yml`,
     and `signing-event.yml` so the default `GITHUB_TOKEN` has no write permissions in those jobs.
