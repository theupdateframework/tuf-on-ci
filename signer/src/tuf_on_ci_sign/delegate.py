# Copyright 2023 Google LLC

"""tuf-on-ci-delegate: A command line tool to modify TUF-on-CI delegations"""

from __future__ import annotations

import copy
import logging
import os
import re
from copy import deepcopy

import click
from securesystemslib.signer import (
    KEY_FOR_TYPE_AND_SCHEME,
    AWSSigner,
    AzureSigner,
    GCPSigner,
    Key,
    SigstoreKey,
    SSlibKey,
)

from tuf_on_ci_sign._common import (
    application_update_reminder,
    bold,
    get_repo_name,
    get_signing_key_input,
    git_expect,
    push_changes,
    signing_event,
)
from tuf_on_ci_sign._signer_repository import (
    OfflineConfig,
    OnlineConfig,
    SignerRepository,
    SignerState,
    set_key_field,
)
from tuf_on_ci_sign._user import User

# sigstore is not a supported key by default
KEY_FOR_TYPE_AND_SCHEME[("sigstore-oidc", "Fulcio")] = SigstoreKey

TAG_KEYOWNER = "x-tuf-on-ci-keyowner"
TAG_ONLINE_URI = "x-tuf-on-ci-online-uri"

logger = logging.getLogger(__name__)


def _get_offline_input(
    role: str,
    config: OfflineConfig,
) -> tuple[OfflineConfig, Key | None]:
    config = copy.deepcopy(config)
    click.echo(f"\nConfiguring role {role}")
    username_re = re.compile("^\\@[0-9a-zA-Z\\-]+$")

    def verify_signers(response: str) -> list[str]:
        # The list is presented in brackets [], if users tries to
        # respond with a list like expression, clear that.
        response = response.strip("[]")
        if not response:
            raise click.BadParameter("Must have at least one signer")

        signers: list[str] = []
        for s in response.split(","):
            s = s.strip().lower()
            if not s.startswith("@"):
                s = f"@{s}"

            if not re.match(username_re, s):
                raise click.BadParameter(f"Invalid username {s}")
            signers.append(s)

        return signers

    online_key = None
    while True:
        click.echo(
            f" 1. Configure signers: [{', '.join(config.signers)}], "
            f"requiring {config.threshold} signatures"
        )
        click.echo(
            f" 2. Configure expiry: Role expires in {config.expiry_period} days, "
            f"re-signing starts {config.signing_period} days before expiry"
        )
        choice = click.prompt(
            bold("Please choose an option or press enter to continue"),
            type=click.IntRange(0, 2),
            default=0,
            show_default=False,
        )
        if choice == 0:
            break
        if choice == 1:
            # if role is not root, allow online keys
            if role in ["root"]:
                config.signers = click.prompt(
                    bold(f"Please enter list of {role} signers"),
                    default=", ".join(config.signers),
                    value_proc=verify_signers,
                )
            else:
                click.echo("Choose what keytype to use:")
                click.echo("1. Configure offline signers:")
                click.echo("2. Configure online signers")
                signer_choice = click.prompt(
                    bold("Please choose an option or press enter to continue"),
                    type=click.IntRange(1, 2),
                )

                if signer_choice == 1:
                    config.signers = click.prompt(
                        bold(f"Please enter list of {role} signers"),
                        default=", ".join(config.signers),
                        value_proc=verify_signers,
                    )
                elif signer_choice == 2:
                    toplevel = git_expect(["rev-parse", "--show-toplevel"])
                    settings_path = os.path.join(toplevel, ".tuf-on-ci-sign.ini")
                    user_config = User(settings_path)
                    online_key = _collect_online_key(user_config)
                    uri = online_key.unrecognized_fields[TAG_ONLINE_URI]
                    config.signers = [uri]

            if len(config.signers) == 1:
                config.threshold = 1
            else:
                config.threshold = click.prompt(
                    bold(f"Please enter {role} threshold"),
                    type=click.IntRange(1, len(config.signers)),
                    default=config.threshold,
                )

        elif choice == 2:
            config.expiry_period = click.prompt(
                bold(f"Please enter {role} expiry period in days"),
                type=int,
                default=config.expiry_period,
            )
            config.signing_period = click.prompt(
                bold(f"Please enter {role} signing period in days"),
                type=int,
                default=config.signing_period,
            )

    return (config, online_key)


def _sigstore_import(pull_remote: str) -> Key:
    # WORKAROUND: build sigstore key and uri here since there is no import yet
    issuer = "https://token.actions.githubusercontent.com"
    repo = get_repo_name(pull_remote)

    id = f"https://github.com/{repo}/.github/workflows/online-sign.yml@refs/heads/main"
    key = SigstoreKey(
        "abcd", "sigstore-oidc", "Fulcio", {"issuer": issuer, "identity": id}
    )
    set_key_field(key, "online-uri", "sigstore:")
    return key


def _get_online_input(config: OnlineConfig, user_config: User) -> OnlineConfig:
    config = copy.deepcopy(config)
    click.echo("\nConfiguring online roles")
    while True:
        keyuri = config.key.unrecognized_fields[TAG_ONLINE_URI]
        click.echo(f" 1. Configure online key: {keyuri}")
        click.echo(
            f" 2. Configure timestamp: Expires in {config.timestamp_expiry} days,"
            f" re-signing starts {config.timestamp_signing} days before expiry"
        )
        click.echo(
            f" 3. Configure snapshot: Expires in {config.snapshot_expiry} days, "
            f"re-signing starts {config.snapshot_signing} days before expiry"
        )
        choice = click.prompt(
            bold("Please choose an option or press enter to continue"),
            type=click.IntRange(0, 3),
            default=0,
            show_default=False,
        )
        if choice == 0:
            break
        if choice == 1:
            config.key = _collect_online_key(user_config)
        if choice == 2:
            config.timestamp_expiry = click.prompt(
                bold("Please enter timestamp expiry in days"),
                type=int,
                default=config.timestamp_expiry,
            )
            config.timestamp_signing = click.prompt(
                bold("Please enter timestamp signing period in days"),
                type=int,
                default=config.timestamp_signing,
            )
        if choice == 3:
            config.snapshot_expiry = click.prompt(
                bold("Please enter snapshot expiry in days"),
                type=int,
                default=config.snapshot_expiry,
            )
            config.snapshot_signing = click.prompt(
                bold("Please enter snapshot signing period in days"),
                type=int,
                default=config.snapshot_signing,
            )

    return config


def _collect_online_key(user_config: User) -> Key:
    # TODO use value_proc argument to validate the input

    while True:
        click.echo(" 1. Sigstore")
        click.echo(" 2. Google Cloud KMS")
        click.echo(" 3. Azure Key Vault")
        click.echo(" 4. AWS KMS")
        choice = click.prompt(
            bold("Please select online key type"),
            type=click.IntRange(0, 4),
            default=1,
            show_default=True,
        )
        if choice == 1:
            return _sigstore_import(user_config.pull_remote)
        if choice == 2:
            key_id = _collect_string("Enter a Google Cloud KMS key id")
            try:
                uri, key = GCPSigner.import_(key_id)
                set_key_field(key, "online-uri", uri)
                return key
            except Exception as e:
                raise click.ClickException(
                    f"Failed to read Google Cloud KMS key: {e}"
                ) from e
        if choice == 3:
            vault_name = _collect_string("Enter Azure vault name")
            key_name = _collect_string("Enter key name")
            try:
                uri, key = AzureSigner.import_(vault_name, key_name)
                set_key_field(key, "online-uri", uri)
                return key
            except Exception as e:
                raise click.ClickException(
                    f"Failed to read Azure Keyvault key: {e}"
                ) from e
        if choice == 4:
            key_id = _collect_string("Enter AWS KMS key id")
            scheme = _collect_key_scheme()
            try:
                uri, key = AWSSigner.import_(key_id, scheme)
                set_key_field(key, "online-uri", uri)
                return key
            except Exception as e:
                raise click.ClickException(f"Failed to read AWS KMS key: {e}") from e
        if choice == 0:
            # This could be generic support, but for now it's a hidden test key.
            # key value 1d9a024348e413892aeeb8cc8449309c152f48177200ee61a02ae56f450c6480
            uri = f"file2:{os.getenv('TUF_ON_CI_TEST_KEY')}"
            pub_key = "fa472895c9756c2b9bcd1440bf867d0fa5c4edee79e9792fa9822be3dd6fcbb3"
            return SSlibKey(
                "cda7a53138556e7c0d1737e4ba32868f3cf287e78ab9366c820115ce11383d34",
                "ed25519",
                "ed25519",
                {"public": pub_key},
                {TAG_ONLINE_URI: uri},
            )


def _collect_string(prompt: str) -> str:
    while True:
        if data := click.prompt(bold(prompt), default=""):
            return data


def _collect_key_scheme() -> str:
    scheme_choices = {
        1: {"ssllib": "ecdsa-sha2-nistp256", "aws": "ECDSA_SHA_256"},
        2: {"ssllib": "ecdsa-sha2-nistp384", "aws": "ECDSA_SHA_384"},
        3: {"ssllib": "ecdsa-sha2-nistp512", "aws": "ECDSA_SHA_512"},
        4: {"ssllib": "rsassa-pss-sha256", "aws": "RSASSA_PSS_SHA_256"},
        5: {"ssllib": "rsassa-pss-sha384", "aws": "RSASSA_PSS_SHA_384"},
        6: {"ssllib": "rsassa-pss-sha512", "aws": "RSASSA_PSS_SHA_512"},
        7: {"ssllib": "rsa-pkcs1v15-sha256", "aws": "RSASSA_PKCS1_V1_5_SHA_256"},
        8: {"ssllib": "rsa-pkcs1v15-sha384", "aws": "RSASSA_PKCS1_V1_5_SHA_384"},
        9: {"ssllib": "rsa-pkcs1v15-sha512", "aws": "RSASSA_PKCS1_V1_5_SHA_512"},
    }

    for key, value in scheme_choices.items():
        click.echo(f"{key}. {value['aws']}")
    choice = click.prompt(
        bold("Please select AWS key scheme"),
        type=click.IntRange(1, 9),
        default=1,
        show_default=True,
    )
    return scheme_choices[choice]["ssllib"]


def _init_repository(repo: SignerRepository) -> bool:
    click.echo("Creating a new TUF-on-CI repository")

    root_config, _ = _get_offline_input(
        "root", OfflineConfig([repo.user.name], 1, 365, 60)
    )
    targets_config, _ = _get_offline_input("targets", deepcopy(root_config))

    # As default we offer sigstore online key(s)
    keys = _sigstore_import(repo.user.pull_remote)
    default_config = OnlineConfig(
        keys, 2, 1, root_config.expiry_period, root_config.signing_period
    )
    online_config = _get_online_input(default_config, repo.user)

    key = None
    if (
        repo.user.name in root_config.signers
        or repo.user.name in targets_config.signers
    ):
        key = get_signing_key_input()

    repo.set_role_config("root", root_config, key)
    repo.set_role_config("targets", targets_config, key)
    repo.set_online_config(online_config)
    return True


def _update_online_roles(repo: SignerRepository) -> bool:
    click.echo("Modifying online roles")

    config = repo.get_online_config()
    new_config = _get_online_input(config, repo.user)
    if new_config == config:
        return False

    repo.set_online_config(new_config)
    return True


def _update_offline_role(repo: SignerRepository, role: str) -> bool:
    config = repo.get_role_config(role)
    online_key = None
    if not config:
        # Non existent role
        click.echo(f"Creating a new delegation for {role}")
        new_config, online_key = _get_offline_input(
            role, OfflineConfig([repo.user.name], 1, 365, 60)
        )
    else:
        click.echo(f"Modifying delegation for {role}")
        new_config, online_key = _get_offline_input(role, config)
        if new_config == config:
            return False

    key = None
    if online_key is None:
        if repo.user.name in new_config.signers:
            key = get_signing_key_input()
    else:
        key = online_key

    repo.set_role_config(role, new_config, key)
    return True


@click.command()  # type: ignore[arg-type]
@click.version_option()
@click.option("-v", "--verbose", count=True, default=0)
@click.option("--push/--no-push", default=True)
@click.option("--force-compliant-keyids", hidden=True, is_flag=True)
@click.argument("event-name", metavar="SIGNING-EVENT")
@click.argument("role", required=False)
def delegate(
    verbose: int,
    push: bool,
    force_compliant_keyids: bool,
    event_name: str,
    role: str | None,
):
    """Tool for modifying TUF-on-CI delegations."""
    logging.basicConfig(level=logging.WARNING - verbose * 10)

    application_update_reminder()

    toplevel = git_expect(["rev-parse", "--show-toplevel"])
    settings_path = os.path.join(toplevel, ".tuf-on-ci-sign.ini")
    user_config = User(settings_path)

    with signing_event(event_name, user_config) as repo:
        if repo.state == SignerState.UNINITIALIZED:
            changed = _init_repository(repo)
        else:
            if role is None:
                role = click.prompt(bold("Enter name of role to modify"))

            if force_compliant_keyids:
                changed = repo.force_compliant_keyids(role)
            elif role in ["timestamp", "snapshot"]:
                changed = _update_online_roles(repo)
            else:
                changed = _update_offline_role(repo, role)

        if changed:
            if role:
                msg = f"'{role}' role/delegation change"
            else:
                msg = "Initial root and targets"
            git_expect(["add", "metadata/"])
            git_expect(["commit", "-m", msg, "--signoff", "--", "metadata"])

            if repo.unsigned:
                click.echo(f"Your signature is required for role(s) {repo.unsigned}.")

                for rolename in repo.unsigned:
                    click.echo(repo.status(rolename))
                    repo.sign(rolename)

                git_expect(["add", "metadata/"])
                git_expect(
                    ["commit", "-m", f"Signed by {user_config.name}", "--signoff"]
                )
            if push:
                push_changes(user_config, event_name, msg)
            else:
                # TODO: deal with existing branch?
                click.echo(f"Creating local branch {event_name}")
                git_expect(["branch", event_name])
        else:
            click.echo("Nothing to do")
