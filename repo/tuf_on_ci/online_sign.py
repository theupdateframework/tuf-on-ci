# Copyright 2023 Google LLC

"""Command line online signing tool for TUF-on-CI"""

import logging
import subprocess

import click

from tuf_on_ci._repository import CIRepository

logger = logging.getLogger(__name__)


def _git(cmd: list[str]) -> subprocess.CompletedProcess:
    cmd = [
        "git",
        "-c",
        "user.name=tuf-on-ci",
        "-c",
        "user.email=41898282+github-actions[bot]@users.noreply.github.com",
        *cmd,
    ]
    proc = subprocess.run(cmd, check=True, text=True)
    logger.debug("%s:\n%s", cmd, proc.stdout)
    return proc


@click.command()  # type: ignore[arg-type]
@click.option("-v", "--verbose", count=True, default=0)
@click.option("--push/--no-push", default=False)
@click.option("--role", default="")
def online_sign(verbose: int, push: bool, role: str) -> None:
    """Update The TUF snapshot and timestamp if needed

    If role is provided, that role is updated instead.

    Create a commit with the updated role changes (if any).
    If --push, the commit is pushed to origin.

    A new snapshot will be created if
    * snapshot content has changed
    * or snapshot is in signing period
    * or snapshot is currently not correctly signed

    A new timestamp will be created if
    * A new snapshot was created
    * or timestamp is in signing period
    * or timestamp is currently not correctly signed

    Provided role will be updated if
    * Content is changed
    * or role is in signing period
    * or role is currently not correctly signed
    """

    logging.basicConfig(level=logging.WARNING - verbose * 10)
    repo = CIRepository("metadata")
    signed = False

    if role != "":
        repo.sign(role)
        # Execptionn is raised if nothing is signed
        signed = True
        roles = role
        files = [repo._get_filename(role)]
    else:
        valid_snapshot = repo.is_signed("snapshot")
        snapshot_updated, _ = repo.do_snapshot(not valid_snapshot)
        valid_timestamp = repo.is_signed("timestamp")
        timestamp_updated, _ = repo.do_timestamp(not valid_timestamp)
        roles = "snapshot & timestamp" if snapshot_updated else "timestamp"
        signed = timestamp_updated
        files = ["metadata/timestamp.json", "metadata/snapshot.json"]
    if signed:
        msg = f"Online sign ({roles})"

        click.echo(msg)
        cmd = ["add"]
        cmd.extend(files)
        _git(cmd)
        _git(["commit", "-m", msg, "--signoff"])
        if push:
            _git(["push", "origin", "HEAD"])
    else:
        click.echo("Online signing not needed")
