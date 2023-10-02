# Copyright 2023 Google LLC

"""Command line tool to build a publishable TUF-on-CI repository"""

import logging

import click

from tuf_on_ci._repository import CIRepository

logger = logging.getLogger(__name__)


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
