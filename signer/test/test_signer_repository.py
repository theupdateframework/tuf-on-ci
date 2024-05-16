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


if __name__ == "__main__":
    unittest.main()
