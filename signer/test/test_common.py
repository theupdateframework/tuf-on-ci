"""Tests for tuf_on_ci_sign._common"""

import os
import unittest
from tempfile import TemporaryDirectory

from tuf_on_ci_sign._common import get_repo_name, git

REPO = "theupdateframework/tuf-on-ci"


class TestGetRepoName(unittest.TestCase):
    """Test parsing 'owner/repo' out of a git remote URL"""

    def setUp(self):
        tempdir = TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(tempdir.name)
        git(["init", "--quiet", "."])

    def _with_remote(self, url: str) -> str:
        git(["remote", "add", "origin", url])
        return get_repo_name("origin")

    def test_https_url(self):
        url = f"https://github.com/{REPO}.git"
        self.assertEqual(self._with_remote(url), REPO)

    def test_https_url_without_git_suffix(self):
        # git clone of an https URL stores it verbatim, without a ".git" suffix
        url = f"https://github.com/{REPO}"
        self.assertEqual(self._with_remote(url), REPO)

    def test_ssh_url(self):
        url = f"git@github.com:{REPO}.git"
        self.assertEqual(self._with_remote(url), REPO)

    def test_ssh_url_without_git_suffix(self):
        url = f"git@github.com:{REPO}"
        self.assertEqual(self._with_remote(url), REPO)


if __name__ == "__main__":
    unittest.main()
