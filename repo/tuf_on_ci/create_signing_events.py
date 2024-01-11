# Copyright 2023 Google LLC

"""Command line tool to create signing events for roles that are about to expire"""

import logging
import subprocess
from glob import glob

import click

from tuf_on_ci._repository import CIRepository

logger = logging.getLogger(__name__)


def _git(cmd: list[str]) -> subprocess.CompletedProcess:
    cmd = [
        "git",
        "-c",
        "user.name=TUF-on-CI",
        "-c",
        "user.email=41898282+github-actions[bot]@users.noreply.github.com",
    ] + cmd
    proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
    logger.debug("%s:\n%s", cmd, proc.stdout)
    return proc


@click.command()  # type: ignore[arg-type]
@click.option("-v", "--verbose", count=True, default=0)
@click.option("--push/--no-push", default=False)
def create_signing_events(verbose: int, push: bool) -> None:
    """Create new branches with version bump commits for expiring offline roles

    Note that these offline role versions will not be signed yet.
    If --push, the branches are pushed to origin. Otherwise local branches are
    created.
    """
    logging.basicConfig(level=logging.WARNING - verbose * 10)

    repo = CIRepository("metadata")
    events = []
    for filename in glob("*.json", root_dir="metadata"):
        if filename in ["timestamp.json", "snapshot.json"]:
            continue

        rolename = filename[: -len(".json")]
        version = repo.bump_expiring(rolename)
        if version is None:
            logging.debug("No version bump needed for %s", rolename)
            continue

        msg = f"Periodic version bump: {rolename} v{version}"
        event = f"sign/{rolename}-v{version}"
        ref = f"refs/remotes/origin/{event}" if push else f"refs/heads/{event}"
        _git(["commit", "-m", msg, "--signoff", "--", f"metadata/{rolename}.json"])
        try:
            _git(["show-ref", "--quiet", "--verify", ref])
            logging.debug("Signing event branch %s already exists", event)
        except subprocess.CalledProcessError:
            events.append(event)
            if push:
                _git(["push", "origin", f"HEAD:{event}"])
            else:
                _git(["branch", event])

        # get back to original HEAD (before we commited)
        _git(["reset", "--hard", "HEAD^"])

    # print out list of created event branches
    click.echo(" ".join(events))
