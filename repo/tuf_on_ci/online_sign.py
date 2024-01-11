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
    ] + cmd
    proc = subprocess.run(cmd, check=True, text=True)
    logger.debug("%s:\n%s", cmd, proc.stdout)
    return proc


@click.command()  # type: ignore[arg-type]
@click.option("-v", "--verbose", count=True, default=0)
@click.option("--push/--no-push", default=False)
def online_sign(verbose: int, push: bool) -> None:
    """Update The TUF snapshot and timestamp if needed

    Create a commit with the snapshot and timestamp changes (if any).
    If --push, the commit is pushed to origin.

    A new snapshot will be created if
    * snapshot content has changed
    * or snapshot is in signing period
    * or snapshot is currently not correctly signed

    A new timestamp will be created if
    * A new snapshot was created
    * or timestamp is in signing period
    * or timestamp is currently not correctly signed
    """

    logging.basicConfig(level=logging.WARNING - verbose * 10)
    repo = CIRepository("metadata")
    valid_snapshot = repo.is_signed("snapshot")
    snapshot_updated, _ = repo.do_snapshot(not valid_snapshot)
    valid_timestamp = repo.is_signed("timestamp")
    timestamp_updated, _ = repo.do_timestamp(not valid_timestamp)

    if timestamp_updated:
        roles = "snapshot & timestamp" if snapshot_updated else "timestamp"
        msg = f"Online sign ({roles})"

        click.echo(msg)
        _git(["add", "metadata/timestamp.json", "metadata/snapshot.json"])
        _git(["commit", "-m", msg, "--signoff"])
        if push:
            _git(["push", "origin", "HEAD"])
    else:
        click.echo("Online signing not needed")
