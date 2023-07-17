# Copyright 2023 Google LLC

"""Common helper functions"""

import os
import subprocess
import sys
from collections.abc import Generator
from configparser import ConfigParser
from contextlib import contextmanager
from tempfile import TemporaryDirectory

import click
from securesystemslib.signer import HSMSigner, Key, SigstoreSigner

from playground_sign._signer_repository import SignerRepository


class SignerConfig:
    def __init__(self, path: str):
        config = ConfigParser()
        config.read(path)

        # TODO: create config if missing, ask/confirm values from user
        if not config:
            raise click.ClickException(f"Settings file {path} not found")
        try:
            self.user_name = config["settings"]["user-name"]
            self.pykcs11lib = config["settings"]["pykcs11lib"]
            self.push_remote = config["settings"]["push-remote"]
            self.pull_remote = config["settings"]["pull-remote"]
        except KeyError as e:
            raise click.ClickException(f"Failed to find required setting {e} in {path}")


@contextmanager
def signing_event(
    name: str, config: SignerConfig
) -> Generator[SignerRepository, None, None]:
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
            repo = SignerRepository(
                metadata_dir, base_metadata_dir, config.user_name, get_secret_input
            )
            yield repo
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

    if choice == 1:
        identity = click.prompt(bold("Please enter your email address"))
        click.echo(" 1. GitHub")
        click.echo(" 2. Google")
        click.echo(" 3. Microsoft")
        issuer_id = click.prompt(
            bold("Please choose the identity issuer"),
            type=click.IntRange(1, 3),
            default=1,
        )
        if issuer_id == 1:
            issuer = "https://github.com/login/oauth"
        elif issuer_id == 2:
            issuer = "https://accounts.google.com"
        else:
            issuer = "https://login.microsoftonline.com"
        try:
            _, key = SigstoreSigner.import_(identity, issuer, ambient=False)
        except Exception as e:
            raise click.ClickException(f"Failed to create Sigstore key: {e}")
    else:
        click.prompt(
            bold("Please insert your Yubikey and press enter"),
            default=True,
            show_default=False,
        )
        try:
            _, key = HSMSigner.import_()
        except Exception as e:
            raise click.ClickException(f"Failed to read HW key: {e}")

    return key


def get_secret_input(secret: str, role: str) -> str:
    # TODO: Fix this so it prints role as well
    # This currently has an issue when it's called from SignerRepository._sign(): The
    # role name is always whatever the first calls argument was...
    # It seems like the role variable becomes part of the closure in _sign() somehow
    # and then the role value gets reused in later calls.
    msg = f"Enter {secret} to sign"

    # special case for tests -- prompt() will lockup trying to hide STDIN:
    if not sys.stdin.isatty():
        return sys.stdin.readline().rstrip()

    return click.prompt(bold(msg), hide_input=True)


def git(cmd: list[str]) -> str:
    cmd = ["git"] + cmd
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
    cmd = ["git"] + cmd
    subprocess.run(cmd, check=True, text=True)


def bold(text: str) -> str:
    return click.style(text, bold=True)


def bold_blue(text: str) -> str:
    return click.style(text, bold=True, fg="bright_blue")
