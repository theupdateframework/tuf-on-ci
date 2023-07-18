import unittest

from tuf_on_ci._repository import CIRepository


class TestCIRepository(unittest.TestCase):
    def test_non_existing_repo(self):
        repo = CIRepository("/tmp/no_such_file")
        self.assertRaises(ValueError, repo.open, "root")

    def test_signing_expiry_days_root(self):
        repo = CIRepository("test/test_repo1")

        signing_days, expiry_days = repo.signing_expiry_period("root")
        self.assertEqual(signing_days, 60)
        self.assertEqual(expiry_days, 365)

    def test_signing_expiry_days_targets(self):
        repo = CIRepository("test/test_repo1")

        signing_days, expiry_days = repo.signing_expiry_period("targets")
        self.assertEqual(signing_days, 40)
        self.assertEqual(expiry_days, 123)

    def test_signing_expiry_days_role(self):
        repo = CIRepository("test/test_repo2")

        signing_days, expiry_days = repo.signing_expiry_period("timestamp")
        self.assertEqual(signing_days, 6)
        self.assertEqual(expiry_days, 40)

    def test_default_signing_days(self):
        repo = CIRepository("test/test_repo1")

        signing_days, expiry_days = repo.signing_expiry_period("timestamp")
        self.assertEqual(signing_days, 2)
        self.assertEqual(expiry_days, 4)

    # def test_bump_expires_expired(self):
    #     repo = CIRepository("test/test_repo1")
    #     ver = repo.bump_expiring("timestamp")
    #     self.assertEqual(ver, 2)


if __name__ == "__main__":
    unittest.main()
