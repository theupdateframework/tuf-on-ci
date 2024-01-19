# Copyright 2012 - 2023, New York University and the TUF contributors
# Copyright 2024 Google LLC

"""Command line testing client for a tuf-on-ci repository"""

import logging
import os
from tempfile import TemporaryDirectory, mkdtemp
import shutil
import click

from tuf.ngclient import Updater


# TODO:
# * Enable support for sigstore signatures
# * Add feature to download a specific file
# * optionally test with cached metadata?

@click.command()
@click.option("-v", "--verbose", count=True, default=0)
@click.option("-m", "--metadata-url", type=str, required=True)
@click.option("-a", "--artifact-url", type=str, required=True)
@click.option("-t", "--root", default="metadata/root_history/1.root.json", help="root metadata to populate client cache")
@click.option("-t", "--metadata-cache", type=str, help="directory with an existing client cache that should be used")
def client(verbose: int, metadata_url: str, artifact_url: str, root: str, metadata_cache: str | None) -> None:
    """Test client for tuf-on-ci"""

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
            # pre-populate the client cache with just a root file
            shutil.copy(root, os.path.join(metadata_dir, "root.json"))

        # For now, just confirm we can get up-to-date top level metadata from remote
        updater = Updater(metadata_dir, metadata_url, artifact_dir, artifact_url)
        updater.refresh()
