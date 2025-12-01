# Copyright 2023 Google LLC

"""Shared git utilities for TUF-on-CI"""

import logging
import subprocess

logger = logging.getLogger(__name__)


def _git(cmd: list[str]) -> subprocess.CompletedProcess:
    """Execute a git command with TUF-on-CI user configuration"""
    cmd = [
        "git",
        "-c",
        "user.name=TUF-on-CI",
        "-c",
        "user.email=41898282+github-actions[bot]@users.noreply.github.com",
        *cmd,
    ]
    proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
    logger.debug("%s:\n%s", cmd, proc.stdout)
    return proc


def _get_base_branch(remote: str = "origin") -> str:
    """Get base branch by auto-detecting from git remote

    Args:
        remote: The git remote name (defaults to "origin")

    Returns:
        The name of the base branch
    """
    try:
        # Try to auto-detect default branch from git remote
        result = _git(["symbolic-ref", f"refs/remotes/{remote}/HEAD"])
        # Output is like 'refs/remotes/origin/main'
        ref = result.stdout.strip()
        branch = ref.split("/")[-1]
        logger.debug("Auto-detected base branch: %s", branch)
        return branch
    except (subprocess.CalledProcessError, IndexError):
        logger.debug("Failed to auto-detect base branch, defaulting to 'main'")
        return "main"
