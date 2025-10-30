# Copyright 2023 Google LLC

"""Command line tool to build a publishable TUF-on-CI repository"""

import logging
import os
from datetime import UTC, datetime, timedelta
from urllib import parse

import click
from tuf.api.metadata import Root, Signed, Targets

from tuf_on_ci._git_utils import _git
from tuf_on_ci._repository import CIRepository
from tuf_on_ci._version import __version__

logger = logging.getLogger(__name__)


def build_description(repo: CIRepository) -> str:
    lines = [
        "## TUF Repository state",
        "",
        "| Role | Signing starts | Expires | Signers |",
        "| - | - | - | - |",
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
            owner = key.unrecognized_fields.get("x-tuf-on-ci-keyowner", "_online key_")
            signers.append(owner)

        delegate: Signed = repo.open(rolename).signed
        if rolename == "timestamp":
            json_link = f"{rolename}.json"
        else:
            json_link = f"{delegate.version}.{rolename}.json"
        expiry = delegate.expires
        signing_days, _ = repo.signing_expiry_period(rolename)
        signing = expiry - timedelta(days=signing_days)
        signing_date = signing.strftime("%Y-%m-%d")

        name_str = f'{rolename} (<a href="{json_link}">json</a>)'
        threshold_str = f"{role.threshold} of {len(signers)}"
        signer_str = f"{', '.join(signers)} ({threshold_str} required)"

        lines.append(f"| {name_str} | {signing_date} | {expiry} UTC | {signer_str} |")

    now = datetime.now(UTC).isoformat(timespec="minutes")
    head = _git(["rev-parse", "HEAD"]).stdout.strip()

    url = parse.urlparse(_git(["config", "--get", "remote.origin.url"]).stdout.strip())
    owner_project = url.path.removesuffix(".git")
    _, _, project = owner_project.rpartition("/")
    project_link = f"https://github.com{owner_project}"

    commit_link = f"[{head[:7]}]({project_link}/tree/{head})"
    tuf_on_ci_url = "https://github.com/theupdateframework/tuf-on-ci"

    lines.append(f"\n_Generated {now} from")
    lines.append(f"[{project}]({project_link}) commit {commit_link}")
    lines.append(f"by [TUF-on-CI]({tuf_on_ci_url}) v{__version__}._")

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
