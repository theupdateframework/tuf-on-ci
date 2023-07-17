import os
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import click
from tuf.api.metadata import TargetFile
from tuf.ngclient import Updater

# The repository is maintained at
# https://jku.github.io/playground-tuf-minimal/
# and published to BASE_URL:
BASE_URL = "https://jku.github.io/playground-tuf-minimal/repository"
METADATA_DIR = f"{Path.home()}/.local/share/playground-tuf-minimal"
CLIENT_ROOT = f"{os.path.dirname(os.path.abspath(__file__))}/root.json"


def _fetch_index(updater: Updater, project: str) -> Dict[str, Dict[str, TargetFile]]:
    """Fetch targets for a project"""

    targets: Dict[str, Dict[str, TargetFile]] = defaultdict(dict)

    # Hack with ngclient internal details until implementation of
    # https://github.com/theupdateframework/python-tuf/issues/1995
    # We take advantage of knowledge that targets metadata is "targets"

    # Make a search that forces targets metadata to be loaded
    updater.get_targetinfo("")
    if not updater._trusted_set.targets:
        return targets

    # Only return targetFiles for this project
    for target in updater._trusted_set.targets.signed.targets.values():
        try:
            proj, prod, ver, _ = target.path.split("/")
        except ValueError:
            continue # not well formed artifact target path
        if proj != project:
            continue
        targets[prod][ver] = target

    return targets

def _version_sort(versions: Iterable) -> List:
    """Sort list of strings using version number sort"""
    versions = list(versions)
    versions.sort(key=lambda s: [int(u) for u in s.split(".")])
    return versions


def _find_current_artifact(versions: Dict[str, TargetFile]) -> Optional[TargetFile]:
    """Return current version string when given a dict where keys are version strings"""
    if not versions:
        return None

    version_strs = _version_sort(versions.keys())
    return versions[version_strs[-1]]


def _download_artifact(updater: Updater, target: TargetFile) -> Optional[str]:
    """Download and store artifact"""
    # use the plain filename as local filename
    fname = target.path.split("/")[-1]
    return updater.download_target(target, filepath=fname)


def _init_updater() -> Updater:
    """initialize local updater dir, return configured Updater"""
    if not os.path.isdir(METADATA_DIR):
        os.makedirs(METADATA_DIR)

    if not os.path.isfile(f"{METADATA_DIR}/root.json"):
        shutil.copy(CLIENT_ROOT, f"{METADATA_DIR}/root.json")

    return Updater(
        metadata_dir=METADATA_DIR,
        metadata_base_url=f"{BASE_URL}/metadata/",
        target_base_url=f"{BASE_URL}/content/",
        target_dir="./",
    )


@click.group()
def main() -> None:
    pass


@main.command()
@click.argument("product", required=True)
def download(product: str):
    # Figure out project name, product name and version
    version = None
    if "=" in product:
        product, version = product.split("=")
    project = product
    if "/" in product:
        project, product = product.split("/")

    print(f"Downloading {project} / {product} = {version}...")

    updater = _init_updater()
    index = _fetch_index(updater, project)
    if not index:
        raise click.ClickException(f"Project {project} not found.")

    versions = index.get(product)
    if not versions:
        raise click.ClickException(f"Product {product} not found.")

    if version is None:
        target = _find_current_artifact(versions)
    else:
        target = versions.get(version)

    if not target:
        raise click.ClickException(f"Version {version} not found.")

    filename = _download_artifact(updater, target)
    if not filename:
        raise click.ClickException(f"Artifact {target.path} not found.")

    print(f"Downloaded {filename}")


@main.command("list")
@click.argument("project", required=True)
def list_(project: str):
    print(f"Listing releases for {project}...")
    updater = _init_updater()
    index = _fetch_index(updater, project)
    if not index:
        raise click.ClickException(f"Project {project} not found.")

    for product, versions in index.items():
        if not versions:
            continue
        # print versions in sorted order
        version_strs = _version_sort(versions.keys())
        print(f"* {product}={version_strs[-1]}, all releases: {version_strs}")


if __name__ == "__main__":

    main()
