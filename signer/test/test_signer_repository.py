import unittest

from tuf_on_ci_sign._signer_repository import build_paths, SignerRepository

class TestUser(unittest.TestCase):
    """Test delegate path generation"""

    def test_build_paths(self):
       paths = build_paths("myrole", SignerRepository.MAX_DEPTH)
       self.assertEquals(paths, ['myrole/*', 'myrole/*/*', 'myrole/*/*/*', 'myrole/*/*/*/*'])

if __name__ == "__main__":
    unittest.main()
