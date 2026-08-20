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
