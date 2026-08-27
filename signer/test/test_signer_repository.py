import unittest

from securesystemslib.signer import SSlibKey

from tuf_on_ci_sign._signer_repository import (
    SignerRepository,
    build_paths,
    set_key_field,
)


class TestUser(unittest.TestCase):
    """Test delegate path generation"""

    def test_build_paths(self):
        paths = build_paths("myrole", SignerRepository.MAX_DEPTH)
        self.assertEqual(
            paths, ["myrole/*", "myrole/*/*", "myrole/*/*/*", "myrole/*/*/*/*"]
        )

    def test_set_key_field(self):
        """Test that set_key_field() modifies the keyid as defined in specification"""
        key = SSlibKey("abcd", "ed25519", "ed25519", {"public": "abcde"})
        expected_id = "3e5e819246b51532a5533efb5d7c3e18ca8e7a7f4d2267644c3e2298ac81de18"

        self.assertEqual(key.keyid, "abcd")
        set_key_field(key, "keyowner", "@testuser")
        self.assertEqual(key.keyid, expected_id)

    def test_mldsa_key_metadata(self):
        """Test that ML-DSA keys in metadata deserialize correctly."""
        from tuf.api.metadata import Metadata, Root

        root = Root()
        mldsa_key = SSlibKey(
            "mldsa_key_id",
            "ml-dsa",
            "ml-dsa-44/1",
            {"public": "some_pub_bytes"},
        )
        root.add_key(mldsa_key, "root")
        md = Metadata(root)
        md_bytes = md.to_bytes()
        reloaded_md = Metadata[Root].from_bytes(md_bytes)
        self.assertIn("mldsa_key_id", reloaded_md.signed.keys)
        self.assertEqual(reloaded_md.signed.keys["mldsa_key_id"].keytype, "ml-dsa")
        self.assertEqual(reloaded_md.signed.keys["mldsa_key_id"].scheme, "ml-dsa-44/1")


if __name__ == "__main__":
    unittest.main()


class TestDelegationStatusLines(unittest.TestCase):
    """Test the change description produced for online delegations"""

    def _repo(self, mutate) -> SignerRepository:
        """Build a signer repository from the test repo, with root.json mutated.

        Only _dir and _prev_dir are needed to produce delegation status lines,
        so the signing event state that __init__ would look for is not set up.
        """
        import json
        import os
        import shutil
        from tempfile import mkdtemp

        src = os.path.join(os.path.dirname(__file__), "..", "..", "repo", "test")
        src = os.path.join(src, "test_repo1")

        prev_dir = mkdtemp()
        cur_dir = mkdtemp()
        self.addCleanup(shutil.rmtree, prev_dir)
        self.addCleanup(shutil.rmtree, cur_dir)
        for d in (prev_dir, cur_dir):
            path = os.path.join(d, "root.json")
            shutil.copyfile(os.path.join(src, "root.json"), path)
            with open(path) as f:
                root = json.load(f)
            # Delegation changes are only described from v2 onwards: at v1 there
            # is no previous delegation set to compare against.
            root["signed"]["version"] = 2
            if d == cur_dir:
                mutate(root["signed"])
            with open(path, "w") as f:
                json.dump(root, f)

        repo = SignerRepository.__new__(SignerRepository)
        repo._dir = cur_dir
        repo._prev_dir = prev_dir
        return repo

    def test_expiry_period_change_is_described(self):
        """A changed online expiry period is reported as such, not as signers."""

        def mutate(signed):
            signed["roles"]["timestamp"]["x-tuf-on-ci-expiry-period"] = 10

        lines = self._repo(mutate)._delegation_status_lines("root")

        self.assertIn(" * Modified online delegations timestamp & snapshot", lines)
        self.assertIn("   * Expiry period: 10 days (was: 4 days)", lines)
        # The signers did not change, so they should not be described as changed.
        self.assertFalse([line for line in lines if "Signers:" in line])

    def test_threshold_change_is_described(self):
        """A changed threshold still reports signers, with a closed paren."""

        def mutate(signed):
            signed["roles"]["timestamp"]["threshold"] = 2

        lines = self._repo(mutate)._delegation_status_lines("root")

        signer_lines = [line for line in lines if "Signers:" in line or "was:" in line]
        self.assertEqual(len(signer_lines), 2)
        self.assertTrue(signer_lines[1].rstrip().endswith(")"), signer_lines[1])

    def test_unchanged_delegation_is_not_reported(self):
        def mutate(signed):
            pass

        lines = self._repo(mutate)._delegation_status_lines("root")

        self.assertFalse([line for line in lines if "Modified" in line])
