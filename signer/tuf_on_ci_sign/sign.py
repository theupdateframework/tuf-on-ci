# Copyright 2023 Google LLC

"""tuf-on-ci-sign: A command line signing tool for TUF-on-CI signing events"""

import logging
import os

import click

from tuf_on_ci_sign._common import (
    bold,
    get_signing_key_input,
    git_echo,
    git_expect,
    signing_event,
)
from tuf_on_ci_sign._signer_repository import SignerState
from tuf_on_ci_sign._user import User

logger = logging.getLogger(__name__)


@click.command()  # type: ignore[arg-type]
@click.option("-v", "--verbose", count=True, default=0)
@click.option("--push/--no-push", default=True)
@click.argument("event-name", metavar="signing-event")
def sign(verbose: int, push: bool, event_name: str):
    """Signing tool for TUF-on-CI signing events."""
    logging.basicConfig(level=logging.WARNING - verbose * 10)

    toplevel = git_expect(["rev-parse", "--show-toplevel"])
    settings_path = os.path.join(toplevel, ".tuf-on-ci-sign.ini")
    user_config = User(settings_path)

    with signing_event(event_name, user_config) as repo:
        if repo.state == SignerState.UNINITIALIZED:
            click.echo("No metadata repository found")
            changed = False
        elif repo.state == SignerState.INVITED:
            click.echo(
                f"You have been invited to become a signer for role(s) {repo.invites}."
            )
            key = get_signing_key_input()
            for rolename in repo.invites.copy():
                # Modify the delegation
                role_config = repo.get_role_config(rolename)
                assert role_config
                repo.set_role_config(rolename, role_config, key)

            # Sign everything
            if repo.unsigned:
                click.echo(f"Your signature is requested for role(s) {repo.unsigned}.")
                for rolename in repo.unsigned:
                    click.echo(repo.status(rolename))
                    repo.sign(rolename)
            changed = True
        elif repo.state == SignerState.SIGNATURE_NEEDED:
            click.echo(f"Your signature is requested for role(s) {repo.unsigned}.")
            for rolename in repo.unsigned:
                click.echo(repo.status(rolename))
                repo.sign(rolename)
            changed = True
        elif repo.state == SignerState.NO_ACTION:
            changed = False
        else:
            raise NotImplementedError

        if changed:
            git_expect(["add", "metadata"])
            git_expect(["commit", "-m", f"Signed by {user_config.name}", "--signoff"])
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
        else:
            click.echo("Nothing to do.")
