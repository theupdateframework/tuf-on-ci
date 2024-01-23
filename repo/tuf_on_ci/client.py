# Copyright 2012 - 2023, New York University and the TUF contributors
# Copyright 2024 Google LLC

"""Command line testing client for a tuf-on-ci repository"""

import logging
import os
import shutil
import sys
from filecmp import cmp
from tempfile import TemporaryDirectory

import click
from tuf.ngclient import Updater


@click.command()
@click.option("-v", "--verbose", count=True, default=0)
@click.option("-m", "--metadata-url", type=str, required=True)
@click.option("-a", "--artifact-url", type=str, required=True)
@click.option("-e", "--expected-artifact", type=str)
@click.option(
    "-c",
    "--metadata-cache",
    type=str,
    help="Optional client cache dir that client should use",
)
def client(
    verbose: int,
    metadata_url: str,
    artifact_url: str,
    expected_artifact: str | None,
    metadata_cache: str | None,
) -> None:
    """Test client for tuf-on-ci

    Client expects to be run in tuf-on-ci repository (current metadata
    in the sources will be considered the expected expected metadata the
    client should receive from remote)."""

    logging.basicConfig(level=logging.WARNING - verbose * 10)

    with TemporaryDirectory() as client_dir:
        metadata_dir = os.path.join(client_dir, "metadata")
        artifact_dir = os.path.join(client_dir, "artifacts")
        os.mkdir(metadata_dir)
        os.mkdir(artifact_dir)

        if metadata_cache:
            # pre-populate the client cache with given directory
            for fname in os.listdir(metadata_cache):
                fpath = os.path.join(metadata_cache, fname)
                if os.path.isfile(fpath):
                    shutil.copy(fpath, os.path.join(metadata_dir, fname))
        else:
            # pre-populate the client cache with first root version from source
            root = "metadata/root_history/1.root.json"
            shutil.copy(root, os.path.join(metadata_dir, "root.json"))

        # For now, just confirm we can get top level metadata from remote
        updater = Updater(metadata_dir, metadata_url, artifact_dir, artifact_url)
        updater.refresh()
        print("Client metadata update: OK")

        # Verify the received metadata versions are what was expected
        for f in ["root.json", "timestamp.json"]:
            if not cmp(f"metadata/{f}", os.path.join(metadata_dir, f), shallow=False):
                sys.exit(f"Client metadata freshness: {f} failed")
        print("Client metadata freshness: OK")

        if expected_artifact:
            # Test expected artifact existence
            tinfo = updater.get_targetinfo(expected_artifact)
            if not tinfo:
                sys.exit("Expected artifact '{expected_artifact}' not found")

            updater.download_target(tinfo)
            print(f"Expected artifact '{expected_artifact}': OK")
