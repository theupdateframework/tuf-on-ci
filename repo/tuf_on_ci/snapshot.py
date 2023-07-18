# Copyright 2023 Google LLC

"""Command line tool to update snapshot (and timestamp) for TUF-on-CI"""

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
@click.option("--metadata", required=True)
@click.option("--targets", required=True)
@click.argument("publish-dir", required=False)
def snapshot(
    verbose: int, push: bool, metadata: str, targets: str, publish_dir: str | None
) -> None:
    """Update The TUF snapshot based on current repository content

    Create a commit with the snapshot and timestamp changes (if any).
    If --push, the commit is pushed to origin.
    If publish-dir is provided, a repository snapshot is generated into that directory
    """
    logging.basicConfig(level=logging.WARNING - verbose * 10)

    repo = CIRepository("metadata")
    snapshot_updated, _ = repo.do_snapshot()
    if not snapshot_updated:
        click.echo("No snapshot needed")
    else:
        repo.do_timestamp()

        msg = "Snapshot & timestamp"
        _git(["add", "metadata/timestamp.json", "metadata/snapshot.json"])
        _git(["commit", "-m", msg])
        if push:
            _git(["push", "origin", "HEAD"])

    if publish_dir:
        repo.publish(publish_dir, metadata, targets)
        click.echo(f"New repository version published in {publish_dir}")
