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

_css = """body {
    color: #24292e;
    line-height: 1.5;
    font-size: 16px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial,
        sans-serif, "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol";
    line-height: 1.5;
    word-wrap: break-word;
}
a {
    background-color: transparent;
    color: #0366d6;
    text-decoration: none;
}
a:hover {
    text-decoration: underline;
}
table {
    margin-bottom: 16px;
    border-collapse: collapse;
    border-spacing: 0;
    display: block;
    overflow: auto;
    width: 100%;
}
table th {
    font-weight: 600;
}
table td,
table th {
    border: 1px solid #dfe2e5;
    padding: 6px 13px;
}
table tr {
    background-color: #fff;
    border-top: 1px solid #c6cbd1;
}
table tr:nth-child(2n) {
    background-color: #f6f8fa;
}
"""


def build_description(repo: CIRepository) -> str:
    lines = [
        "<!DOCTYPE html>",
        "<html>",
        f"<head><title>TUF Repository State</title><style>{_css}</style></head>",
        "<body>",
        "<h2>TUF Repository state</h2>",
        "<table>",
        "<thead><tr>",
        "<th>Role</th><th>Signing starts</th><th>Expires</th><th>Signers</th>",
        "</tr></thead>",
        "<tbody>",
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
            owner = key.unrecognized_fields.get(
                "x-tuf-on-ci-keyowner", "<i>online key</i>"
            )
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

        lines.append(
            "<tr>"
            f"<td>{name_str}</td>"
            f"<td>{signing_date}</td>"
            f"<td>{expiry} UTC</td>"
            f"<td>{signer_str}</td>"
            "</tr>"
        )

    lines.append("</tbody></table>")
    now = datetime.now(UTC).isoformat(timespec="minutes")
    head = _git(["rev-parse", "HEAD"]).stdout.strip()

    url = parse.urlparse(_git(["config", "--get", "remote.origin.url"]).stdout.strip())
    owner_project = url.path.removesuffix(".git")
    _, _, project = owner_project.rpartition("/")
    project_link = f"https://github.com{owner_project}"

    commit_link = f'<a href="{project_link}/tree/{head}">{head[:7]}</a>'
    tuf_on_ci_url = "https://github.com/theupdateframework/tuf-on-ci"

    lines.append(f"<p><i>Generated {now} from")
    lines.append(f'<a href="{project_link}">{project}</a> commit {commit_link}')
    lines.append(f'by <a href="{tuf_on_ci_url}">TUF-on-CI</a> v{__version__}.</i></p>')

    lines.append("</body>")
    lines.append("</html>")
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

    with open(os.path.join(metadata, "index.html"), "w") as f:
        f.write(build_description(repo))
