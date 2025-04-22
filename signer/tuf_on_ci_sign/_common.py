# Copyright 2023 Google LLC

"""Common helper functions"""

import json
import logging
import os
import subprocess
import webbrowser
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timedelta
from tempfile import TemporaryDirectory
from urllib import parse
from urllib.request import Request, urlopen

import click
from packaging.version import Version
from platformdirs import user_cache_dir
from securesystemslib.signer import HSMSigner, Key, SigstoreSigner

from tuf_on_ci_sign._signer_repository import SignerRepository
from tuf_on_ci_sign._user import User

logger = logging.getLogger(__name__)


@contextmanager
def signing_event(name: str, config: User) -> Generator[SignerRepository, None, None]:
    toplevel = git(["rev-parse", "--show-toplevel"])

    # PyKCS11 (Yubikey support) needs the module path
    # TODO: if config is not set, complain/ask the user?
    if "PYKCS11LIB" not in os.environ:
        os.environ["PYKCS11LIB"] = config.pykcs11lib

    # first, make sure we're up-to-date
    git_expect(["fetch", config.pull_remote])
    try:
        git(["checkout", f"{config.pull_remote}/{name}"])
    except subprocess.CalledProcessError:
        click.echo("Remote branch not found: branching off from main")
        git_expect(["checkout", f"{config.pull_remote}/main"])

    try:
        # checkout the base of this signing event in another directory
        with TemporaryDirectory() as temp_dir:
            base_sha = git_expect(["merge-base", f"{config.pull_remote}/main", "HEAD"])
            event_sha = git_expect(["rev-parse", "HEAD"])
            git_expect(["clone", "--quiet", toplevel, temp_dir])
            git_expect(["-C", temp_dir, "checkout", "--quiet", base_sha])
            base_metadata_dir = os.path.join(temp_dir, "metadata")
            metadata_dir = os.path.join(toplevel, "metadata")

            click.echo(bold_blue(f"Signing event {name} (commit {event_sha[:7]})"))
            yield SignerRepository(metadata_dir, base_metadata_dir, config)
    finally:
        # go back to original branch
        git_expect(["checkout", "-"])


def get_signing_key_input() -> Key:
    click.echo("\nConfiguring signing key")
    click.echo(" 1. Sigstore (OpenID Connect)")
    click.echo(" 2. Yubikey")
    choice = click.prompt(
        bold("Please choose the type of signing key you would like to use"),
        type=click.IntRange(1, 2),
        default=1,
    )

    key: Key
    if choice == 1:
        click.echo(bold("Please authenticate with your Sigstore signing identity"))
        _, key = SigstoreSigner.import_via_auth()
    else:
        click.prompt(
            bold("Please insert your Yubikey and press enter"),
            default=True,
            show_default=False,
        )
        try:
            _, key = HSMSigner.import_()
        except Exception as e:
            raise click.ClickException(f"Failed to read HW key: {e}") from e

    return key


def git(cmd: list[str]) -> str:
    cmd = ["git", *cmd]
    proc = subprocess.run(cmd, capture_output=True, check=True, text=True)
    return proc.stdout.strip()


def git_expect(cmd: list[str]) -> str:
    """Run git, expect success"""
    try:
        return git(cmd)
    except subprocess.CalledProcessError as e:
        print(f"git failure:\n{e.stderr}")
        print(f"\n{e.stdout}")
        raise


def git_echo(cmd: list[str]):
    cmd = ["git", *cmd]
    subprocess.run(cmd, check=True, text=True)


def bold(text: str) -> str:
    return click.style(text, bold=True)


def bold_blue(text: str) -> str:
    return click.style(text, bold=True, fg="bright_blue")


def application_update_reminder() -> None:
    from tuf_on_ci_sign import __version__

    update_file = os.path.join(user_cache_dir("tuf-on-ci-sign"), "pypi_release_version")
    try:
        update_time = os.path.getmtime(update_file)
    except OSError:
        update_time = 0

    try:
        if datetime.fromtimestamp(update_time) + timedelta(days=1) > datetime.now():
            # It's been less than a day since last pypi query
            with open(update_file) as f:
                max_version = Version(f.read())
        else:
            # Find out newest release version from pypi
            request = Request("https://pypi.org/simple/tuf-on-ci-sign/")
            request.add_header("Accept", "application/vnd.pypi.simple.v1+json")
            with urlopen(request, timeout=5) as response:  # noqa: S310
                data = json.load(response)

            max_version = Version("0")
            for ver_str in data["versions"]:
                ver = Version(ver_str)
                if not ver.is_devrelease and not ver.is_prerelease:
                    max_version = max(max_version, ver)

            # store the current version number in cache
            os.makedirs(os.path.dirname(update_file), exist_ok=True)
            with open(update_file, "w") as f:
                f.write(str(max_version))

        if max_version > Version(__version__):
            msg = bold(
                f"tuf-on-ci-sign {__version__} is outdated: New version "
                f"({max_version}) is available"
            )
            print(msg)

    except Exception as e:  # noqa: BLE001
        logger.warning(f"Failed to check current tuf-on-ci-sign version: {e}")


def push_changes(user: User, event_name: str, title: str) -> None:
    """Push the event branch to users push remote"""
    branch = f"{user.push_remote}/{event_name}"
    msg = f"Press enter to push changes to {branch}"
    click.prompt(bold(msg), default=True, show_default=False)
    if user.push_remote == user.pull_remote:
        # maintainer flow: just push to signing event branch
        git_echo(
            [
                "push",
                user.push_remote,
                f"HEAD:refs/heads/{event_name}",
            ]
        )
    else:
        # non-maintainer flow: push to fork, make a PR.
        # NOTE: we force push: this is safe since any existing fork branches
        # have either been merged or are obsoleted by this push
        git_echo(
            [
                "push",
                "--force",
                user.push_remote,
                f"HEAD:refs/heads/{event_name}",
            ]
        )
        # Create PR from fork (push remote) to upstream (pull remote)
        upstream = get_repo_name(user.pull_remote)
        fork = get_repo_name(user.push_remote).replace("/", ":")
        query = parse.urlencode(
            {
                "quick_pull": 1,
                "title": title,
                "template": "signing_event.md",
            }
        )
        pr_url = f"https://github.com/{upstream}/compare/{event_name}...{fork}:{event_name}?{query}"
        if webbrowser.open(pr_url):
            click.echo(bold("Please submit the pull request in your browser."))
        else:
            click.echo(bold(f"Please submit the pull request:\n    {pr_url}"))


def get_repo_name(remote: str) -> str:
    """Return 'owner/repo' string for given GitHub remote"""
    url = parse.urlparse(git_expect(["config", "--get", f"remote.{remote}.url"]))
    owner_repo = url.path[: -len(".git")]
    # ssh-urls are relative URLs according to urllib: host is actually part of
    # path. We don't want the host part:
    _, _, owner_repo = owner_repo.rpartition(":")
    # http urls on the other hand are not relative: remove the leading /
    owner_repo = owner_repo.lstrip("/")

    # sanity check
    owner, slash, repo = owner_repo.partition("/")
    if not owner or slash != "/" or not repo:
        raise RuntimeError(
            "Failed to parse GitHub repository from git URL {url} for remote {remote}"
        )

    return owner_repo
