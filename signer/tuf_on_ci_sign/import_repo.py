# Copyright 2023 Google LLC

"""tuf-on-ci-import: A command line import tool for TUF-on-CI signing events"""

from __future__ import annotations

import json
import logging
import os

import click
from tuf.api.metadata import Key, Role, Signed

from tuf_on_ci_sign._common import (
    bold,
    git_echo,
    git_expect,
    signing_event,
)
from tuf_on_ci_sign._signer_repository import AbortEdit
from tuf_on_ci_sign._user import User

logger = logging.getLogger(__name__)

EXPIRY_KEY = "x-tuf-on-ci-expiry-period"
SIGNING_KEY = "x-tuf-on-ci-signing-period"
ONLINE_URI_KEY = "x-tuf-on-ci-online-uri"
KEYOWNER_KEY = "x-tuf-on-ci-keyowner"


def _update_expiry(obj: Signed | Role, import_data: dict[str, int]):
    if EXPIRY_KEY in import_data and import_data[EXPIRY_KEY] != -1:
        expiry = import_data[EXPIRY_KEY]
    elif EXPIRY_KEY in obj.unrecognized_fields:
        expiry = obj.unrecognized_fields[EXPIRY_KEY]
    elif "x-playground-expiry-period" in obj.unrecognized_fields:
        expiry = obj.unrecognized_fields["x-playground-expiry-period"]
    else:
        # let user know this is needed
        import_data[EXPIRY_KEY] = -1
        return False

    # set the value
    obj.unrecognized_fields[EXPIRY_KEY] = expiry
    # unset legacy playground value
    obj.unrecognized_fields.pop("x-playground-expiry-period", None)

    return True


def _update_signing(obj: Signed | Role, import_data: dict[str, int]):
    if SIGNING_KEY in import_data and import_data[SIGNING_KEY] != -1:
        signing = import_data[SIGNING_KEY]
    elif SIGNING_KEY in obj.unrecognized_fields:
        signing = obj.unrecognized_fields[SIGNING_KEY]
    elif "x-playground-signing-period" in obj.unrecognized_fields:
        signing = obj.unrecognized_fields["x-playground-signing-period"]
    elif "x-playground-expiry-period" in obj.unrecognized_fields:
        # signing-period was not required at some point
        signing = obj.unrecognized_fields["x-playground-expiry-period"] // 2
    else:
        # let user know this is needed
        import_data[SIGNING_KEY] = -1
        return False

    # set the value
    obj.unrecognized_fields[SIGNING_KEY] = signing
    # unset legacy playground value
    obj.unrecognized_fields.pop("x-playground-signing-period", None)

    return True


def _update_keys(keys: dict[str, Key], import_data: dict[str, str]):
    success = True
    undefined = "UNDEFINED ONLINE_URI OR KEYOWNER"
    for key in keys.values():
        if key.keyid in import_data and import_data[key.keyid] != undefined:
            value = import_data[key.keyid]
        elif ONLINE_URI_KEY in key.unrecognized_fields:
            value = key.unrecognized_fields[ONLINE_URI_KEY]
        elif KEYOWNER_KEY in key.unrecognized_fields:
            value = key.unrecognized_fields[KEYOWNER_KEY]
        elif "x-playground-online-uri" in key.unrecognized_fields:
            value = key.unrecognized_fields["x-playground-online-uri"]
        elif "x-playground-keyowner" in key.unrecognized_fields:
            value = key.unrecognized_fields["x-playground-keyowner"]
        else:
            # let user know this is needed
            import_data[key.keyid] = undefined
            success = False
            continue

        # set the value, unset legacy value
        if value.startswith("@"):
            key.unrecognized_fields[KEYOWNER_KEY] = value
            key.unrecognized_fields.pop("x-playground-keyowner", None)
        else:
            key.unrecognized_fields[ONLINE_URI_KEY] = value
            key.unrecognized_fields.pop("x-playground-online-uri", None)

    return success


@click.command()  # type: ignore[arg-type]
@click.option("-v", "--verbose", count=True, default=0)
@click.option("--push/--no-push", default=True)
@click.argument("event-name", metavar="signing-event")
@click.argument("import-file", required=False)
def import_repo(verbose: int, push: bool, event_name: str, import_file: str | None):
    """Repository import tool for TUF-on-CI signing events.

    Works on both unmanaged repositories and legacy playground-repository managed
    repositories.

    \b
    tuf-on-ci-import-repo <EVENT>
        Creates a signing event with all of the import changes or, if there are missing
        custom metadata fields, prints out import file contents that can be filled.

    \b
    tuf-on-ci-import-repo <EVENT> <IMPORTFILE>
        Creates a signing event with all of the import changes using the import file
        to fill in missing custom metadata.
    """
    logging.basicConfig(level=logging.WARNING - verbose * 10)

    toplevel = git_expect(["rev-parse", "--show-toplevel"])
    settings_path = os.path.join(toplevel, ".tuf-on-ci-sign.ini")
    user_config = User(settings_path)

    if import_file:
        with open(import_file) as f:
            import_data = json.load(f)
    else:
        import_data = {}

    with signing_event(event_name, user_config) as repo:
        ok = True
        # handle root and all target files, in order of delegations
        roles = ["root", "targets"]
        for _, _, filenames in os.walk(f"{toplevel}/metadata"):
            for filename in filenames:
                if not filename.endswith(".json"):
                    continue
                rolename = filename[: -len(".json")]
                if rolename in ["root", "timestamp", "snapshot", "targets"]:
                    continue
                roles.append(rolename)

        for rolename in roles:
            if rolename not in import_data:
                import_data[rolename] = {}

            role_data = import_data[rolename]
            if rolename == "root":
                with repo.edit_root() as root:
                    ok = _update_signing(root, role_data) and ok
                    ok = _update_expiry(root, role_data) and ok

                    for online_rolename in ["timestamp", "snapshot"]:
                        role = root.get_delegated_role(online_rolename)
                        ok = _update_signing(role, role_data) and ok
                        ok = _update_expiry(role, role_data) and ok

                    ok = _update_keys(root.keys, role_data) and ok
                    if not ok:
                        raise AbortEdit("Missing values")

            else:
                with repo.edit_targets(rolename) as targets:
                    ok = _update_expiry(targets, role_data) and ok
                    ok = _update_signing(targets, role_data) and ok

                    if targets.delegations:
                        ok = _update_keys(targets.delegations.keys, role_data) and ok
                    if not ok:
                        raise AbortEdit("Missing values")

        if not ok:
            print("Error: Undefined values found. please save this in a file,")
            print("fill in the values and use the file as import-file argument:\n")
            print(json.dumps(import_data, indent=2))
        else:
            # we have updated keys defined in root/targets: make sure they are compliant
            repo.force_compliant_keyids("root")
            repo.force_compliant_keyids("targets")

            git_expect(["add", "metadata"])
            git_expect(
                ["commit", "-m", f"Repo import by {user_config.name}", "--signoff"]
            )

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
                branch = f"{user_config.push_remote}/{event_name}"
                msg = f"Press enter to push signature(s) to {branch}"
                click.prompt(bold(msg), default=True, show_default=False)
                git_echo(
                    [
                        "push",
                        "--progress",
                        user_config.push_remote,
                        f"HEAD:refs/heads/{event_name}",
                    ]
                )
            else:
                # TODO: maybe deal with existing branch?
                click.echo(f"Creating local branch {event_name}")
                git_expect(["branch", event_name])
