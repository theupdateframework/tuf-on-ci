# Copyright 2023 Google LLC

"""Command line tool to build a publishable TUF-on-CI repository"""

import logging
import os

import click
from tuf.api.metadata import Root, Targets

from tuf_on_ci._repository import CIRepository

logger = logging.getLogger(__name__)


def build_description(repo: CIRepository) -> str:
    lines = [
        "## Signers",
        "| Role | required # of signatures | Signers |",
        "| - | - | - |",
    ]
    root = repo.root()
    targets = repo.targets()
    roles: list[tuple[Root | Targets, str]] = [
        (root, "root"),
        (root, "timestamp"),
        (root, "snapshot"),
        (root, "targets"),
    ]
    if targets.delegations and targets.delegations.roles:
        for rolename in targets.delegations.roles:
            roles.append((targets, rolename))

    for delegator, rolename in roles:
        role = delegator.get_delegated_role(rolename)
        keys = [delegator.get_key(keyid) for keyid in role.keyids]
        signers = []
        for key in keys:
            if "x-tuf-on-ci-keyowner" in key.unrecognized_fields:
                signers.append(key.unrecognized_fields["x-tuf-on-ci-keyowner"])
            else:
                signers.append("_online key_")
        lines.append(f"| {rolename} | {role.threshold} | {', '.join(signers)} |")

    return "\n".join(lines)


@click.command()  # type: ignore[arg-type]
@click.option("-v", "--verbose", count=True, default=0)
@click.option("--metadata", required=True)
@click.option("--artifacts")
def build_repository(verbose: int, metadata: str, artifacts: str | None) -> None:
    """Create publishable metadata and artifact directories"""
    logging.basicConfig(level=logging.WARNING - verbose * 10)

    repo = CIRepository("metadata")
    repo.build(metadata, artifacts)

    click.echo(f"Metadata published in {metadata}")
    if artifacts:
        click.echo(f"Artifacts published in {artifacts}")

    with open(os.path.join(metadata, "index.md"), "w") as f:
        f.write(build_description(repo))
