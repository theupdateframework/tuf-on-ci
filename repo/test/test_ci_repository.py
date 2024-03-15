import logging
import unittest
import tempfile
import shutil
import os

from tuf_on_ci._repository import CIRepository


class TestCIRepository(unittest.TestCase):
    def test_non_existing_repo(self):
        repo = CIRepository("no_such_file")
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

    def test_target_loading(self):

        repo_path = "test/test_repo3"
        good_meta = os.path.join(repo_path, "good/metadata")
        temp_dir = tempfile.mkdtemp("_tuf_on_ci")
        temp_meta = os.path.join(temp_dir, "metadata")
        temp_targets = os.path.join(temp_dir, "targets")
        temp_publish = os.path.join(temp_dir, "publish")
        temp_publish_artifactrs = os.path.join(temp_dir, "publish_artifacts")
        os.makedirs(temp_targets)
        os.makedirs(temp_meta)
        src_targets = os.path.join(repo_path, "src_targets")
        try:
            shutil.copytree(good_meta, temp_meta, dirs_exist_ok=True)
            repo = CIRepository(temp_meta, good_meta)
            targets = repo.targets("targets")

            # no targets exist on disk yet, only in metadata
            self.assertIn("tfile1.txt", targets.targets)
            self.assertIn("tfile2.txt", targets.targets)
            # on update, they'll be removed
            repo.update_targets("targets")
            targets = repo.targets("targets")
            self.assertNotIn("tfile1.txt", targets.targets)
            self.assertNotIn("tfile2.txt", targets.targets)

            # now add a file not covered by another role
            shutil.copy(os.path.join(src_targets, "tfile1.txt"), temp_targets)
            # on update, they'll be removed
            repo.update_targets("targets")
            targets = repo.targets("targets")
            self.assertIn("tfile1.txt", targets.targets)
            self.assertEqual(len(targets.targets), 1)

            # now add files covered by another role
            shutil.copytree(os.path.join(src_targets, "levela"), os.path.join(temp_targets, "levela"))
            shutil.copytree(os.path.join(src_targets, "levelb"), os.path.join(temp_targets, "levelb"))

            # it shouldn't be in targets
            repo.update_targets("targets")
            targets = repo.targets("targets")
            self.assertNotIn("levela/filea.txt", targets.targets)
            self.assertNotIn("levelb/fileb.txt", targets.targets)
            self.assertEqual(len(targets.targets), 1)

            # but should be in myrole1
            repo.update_targets("myrole1")
            targets = repo.targets("myrole1")
            self.assertIn("levela/filea.txt", targets.targets)
            self.assertIn("levelb/fileb.txt", targets.targets)

            # if we copy over level1, then targts should pick this up because it's not covered by any othe roles
            shutil.copytree(os.path.join(src_targets, "level1"), os.path.join(temp_targets, "level1"))
            repo.update_targets("targets")
            targets = repo.targets("targets")

            self.assertIn("level1/level2/tfile2.txt", targets.targets)

            # except level1/file1.txt which is covered by myrole2
            self.assertNotIn("level1/file1.txt", targets.targets)
            repo.update_targets("myrole2")
            targets = repo.targets("myrole2")
            self.assertIn("level1/file1.txt", targets.targets)

            repo.build(temp_publish, temp_publish_artifactrs)


        finally:
            print(f"Removing {temp_dir}")
            #shutil.rmtree(temp_dir)

if __name__ == "__main__":
    unittest.main()
