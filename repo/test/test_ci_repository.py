import unittest
import shutil
import os
from tempfile import TemporaryDirectory

from tuf_on_ci._repository import CIRepository
from tuf_on_ci.signing_event import _find_changed_target_roles


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
        with TemporaryDirectory("_tuf_on_ci") as temp_dir:

            temp_meta = os.path.join(temp_dir, "metadata")
            temp_targets = os.path.join(temp_dir, "targets")
            os.makedirs(temp_targets)
            os.makedirs(temp_meta)
            src_targets = os.path.join(repo_path, "src_targets")
            shutil.copytree(good_meta, temp_meta, dirs_exist_ok=True)
            repo = CIRepository(temp_meta, good_meta)
            targets = repo.targets("targets")

            # no targets exist on disk yet, only in metadata
            self.assertIn("tfile1.txt", targets.targets)

            # updating removes them because they're not on disk
            repo.update_targets("targets")
            targets = repo.targets("targets")
            self.assertNotIn("tfile1.txt", targets.targets)

            # adding these files and updating adds them to targets
            shutil.copy(os.path.join(src_targets, "tfile1.txt"), temp_targets)
            repo.update_targets("targets")
            targets = repo.targets("targets")
            self.assertIn("tfile1.txt", targets.targets)


            # now add a file not covered by another role
            shutil.copy(os.path.join(src_targets, "tfile1.txt"), temp_targets)
            # on update, it should be in targets
            repo.update_targets("targets")
            targets = repo.targets("targets")
            self.assertIn("tfile1.txt", targets.targets)
            self.assertEqual(len(targets.targets), 1)

            # targets does not support multiple levels right now
            shutil.copytree(os.path.join(src_targets, "other_dir"), os.path.join(temp_targets, "other_dir"))
            # on update, it should be in targets
            repo.update_targets("targets")
            targets = repo.targets("targets")
            self.assertNotIn("other_dir/otherfile.txt", targets.targets)
            self.assertEqual(len(targets.targets), 1)

            # nothing in myrole until some files are added
            repo.update_targets("myrole")
            targets = repo.targets("myrole")
            self.assertEqual(len(targets.targets), 0)

            shutil.copytree(os.path.join(src_targets, "myrole"), os.path.join(temp_targets, "myrole"))
            repo.update_targets("myrole")
            targets = repo.targets("myrole")
            self.assertEqual(len(targets.targets), 4)
            self.assertIn("myrole/file0.txt", targets.targets)
            self.assertIn("myrole/dir1/dir2/dir3/file3.txt", targets.targets)
            self.assertNotIn("myrole/dir1/dir2/dir3/dir4/file4.txt", targets.targets)

            # existing roles without deep paths are honored (deeper targets are ignored)
            shutil.copytree(os.path.join(src_targets, "oldrole"), os.path.join(temp_targets, "oldrole"))
            repo.update_targets("oldrole")
            targets = repo.targets("oldrole")
            self.assertEqual(len(targets.targets), 1)
            self.assertIn("oldrole/file0.txt", targets.targets)
            self.assertNotIn("oldrole/dir1/file1.txt", targets.targets)

            # changed roles are detected properly
            roles = _find_changed_target_roles(repo, temp_targets, "targets")
            self.assertSetEqual(roles, {'myrole', 'targets', "oldrole"}, "unexpect roles found")


if __name__ == "__main__":
    unittest.main()
