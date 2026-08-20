import os
import platform
import unittest
import unittest.mock
from tempfile import TemporaryDirectory

import click
from securesystemslib.signer import HSMSigner, SSlibKey

from tuf_on_ci_sign import _user
from tuf_on_ci_sign._user import User

# Long lines are ok here
# ruff: noqa: E501
REQUIRED = """
[settings]
user-name = @signer
push-remote = origin
pull-remote = myremote
"""

WITH_PYKCS11LIB = """
[settings]
pykcs11lib = /usr/lib/x86_64-linux-gnu/libykcs11.so
user-name = @signer
push-remote = origin
pull-remote = myremote
"""

MISSING_NAME = """
[settings]
pykcs11lib = /usr/lib/x86_64-linux-gnu/libykcs11.so
push-remote = origin
pull-remote = myremote
"""

NAME_WITH_NO_PREFIX = """
[settings]
pykcs11lib = /usr/lib/x86_64-linux-gnu/libykcs11.so
user-name = signer
push-remote = origin
pull-remote = myremote
"""

REQUIRED_AND_SIGNING_KEYS = """
[settings]
pykcs11lib = /usr/lib/x86_64-linux-gnu/libykcs11.so
user-name = @signer
push-remote = origin
pull-remote = myremote

[signing-keys]
762cb22caca65de5e9b7b6baecb84ca989d337280ce6914b6440aea95769ad93 = hsm:2?label=YubiKey+PIV+%2315835999
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b = file:keys/mykey?encrypted=false
"""

HSM_KEY = SSlibKey(
    "762cb22caca65de5e9b7b6baecb84ca989d337280ce6914b6440aea95769ad93",
    "ecdsa",
    "ecdsa-sha2-nistp256",
    {
        "public": "-----BEGIN PUBLIC KEY-----\nMFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEohqIdE+yTl4OxpX8ZxNUPrg3SL9H\nBDnhZuceKkxy2oMhUOxhWweZeG3bfM1T4ZLnJimC6CAYVU5+F5jZCoftRw==\n-----END PUBLIC KEY-----\n"
    },
)

NONCONFIGURED_KEY = SSlibKey(
    "64eeece964e09c058ef8f9805daca546b01ba4719c80b6fe911b091a7c05124b",
    "ecdsa",
    "ecdsa-sha2-nistp256",
    {
        "public": "-----BEGIN PUBLIC KEY-----\nMFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEu+ebm3VUg6U2b0IIeR6NFZU7uxkL\nR1sVLxV8SEW7G+AMXMasEQf5daxfwVMP1kuEkhGs3mBYLkYXlWDh9BNSxg==\n-----END PUBLIC KEY-----\n"
    },
)

ML_DSA_KEY = SSlibKey(
    "mldsa_key_id",
    "ml-dsa",
    "ml-dsa-44/1",
    {
        "public": "-----BEGIN PUBLIC KEY-----\nMBkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEu+ebm3VUg6U2b0IIeR6NFZU7uxkL\nR1sVLxV8SEW7G+AMXMasEQf5daxfwVMP1kuEkhGs3mBYLkYXlWDh9BNSxg==\n-----END PUBLIC KEY-----\n"
    },
)


class TestUser(unittest.TestCase):
    """Test configuration management and signer caching"""

    def test_required(self):
        with TemporaryDirectory() as tempdir:
            inifile = os.path.join(tempdir, ".tuf-on-ci-sign.ini")
            with open(inifile, "w") as f:
                f.write(WITH_PYKCS11LIB)

            user = User(inifile)
            self.assertEqual(user.name, "@signer")
            self.assertEqual(user.pykcs11lib, "/usr/lib/x86_64-linux-gnu/libykcs11.so")
            self.assertEqual(user.push_remote, "origin")
            self.assertEqual(user.pull_remote, "myremote")

            with open(inifile, "w") as f:
                f.write(NAME_WITH_NO_PREFIX)

            user2 = User(inifile)
            self.assertEqual(user.name, user2.name)

            with open(inifile, "w") as f:
                f.write(MISSING_NAME)
            with self.assertRaises(click.ClickException):
                user = User(inifile)

    def test_pkcs_prober(self):
        with TemporaryDirectory() as tempdir:
            inifile = os.path.join(tempdir, ".tuf-on-ci-sign.ini")
            with open(inifile, "w") as f:
                f.write(REQUIRED)

            nonexistent_pkcs11lib = os.path.join(tempdir, "nonexistent-pkcs11lib")
            mock_pkcs11lib = os.path.join(tempdir, "mock-pkcs11lib")
            with open(mock_pkcs11lib, "w") as f:
                f.write("")

            # mock prober lookup locations so that a library is not found:
            _user.LIBYKCS11_LOCATIONS = {platform.system(): [nonexistent_pkcs11lib]}
            with self.assertRaises(click.ClickException):
                User(inifile)

            # mock prober lookup locations so that a library is found:
            _user.LIBYKCS11_LOCATIONS = {
                platform.system(): [nonexistent_pkcs11lib, mock_pkcs11lib]
            }
            user = User(inifile)
            self.assertEqual(user.pykcs11lib, mock_pkcs11lib)

    def test_signing_keys(self):
        with TemporaryDirectory() as tempdir:
            inifile = os.path.join(tempdir, ".tuf-on-ci-sign.ini")
            statefile = os.path.join(tempdir, "signing-keys.ini")
            with open(inifile, "w") as f:
                f.write(REQUIRED_AND_SIGNING_KEYS)

            user = User(inifile, data_path=statefile)
            # We should get a signer for the configured HSM
            hsm_signer = user.get_signer(HSM_KEY)
            self.assertIsInstance(hsm_signer, HSMSigner)
            self.assertEqual(hsm_signer.token_label, "YubiKey PIV #15835999")
            self.assertEqual(
                hsm_signer.public_key.keyid,
                "762cb22caca65de5e9b7b6baecb84ca989d337280ce6914b6440aea95769ad93",
            )

            # Cache the signer
            user.set_signer(HSM_KEY, hsm_signer)

            # If the signing key is not configured, we expect a generic HSM signer
            # and it should be saved to the machine state file
            other_signer = user.get_signer(NONCONFIGURED_KEY)
            self.assertIsInstance(other_signer, HSMSigner)
            self.assertEqual(
                user._app_data["signing-keys"][NONCONFIGURED_KEY.keyid], "hsm:"
            )

            # verify it was written to state file by reloading
            user3 = User(inifile, data_path=statefile)
            self.assertEqual(
                user3._app_data["signing-keys"][NONCONFIGURED_KEY.keyid], "hsm:"
            )

            # another lookup should return same instance
            second_hsm_signer = user.get_signer(HSM_KEY)
            self.assertIs(hsm_signer, second_hsm_signer)

    @unittest.mock.patch("click.prompt")
    @unittest.mock.patch("securesystemslib.signer.TKeySigner.import_")
    @unittest.mock.patch("securesystemslib.signer.TKeySigner.from_priv_key_uri")
    def test_tkey_key(self, mock_from_uri, mock_import, mock_prompt):
        with TemporaryDirectory() as tempdir:
            inifile = os.path.join(tempdir, ".tuf-on-ci-sign.ini")
            statefile = os.path.join(tempdir, "signing-keys.ini")

            # 1. Test with configured URI in local repo config
            config_with_tkey = (
                REQUIRED_AND_SIGNING_KEYS + "\nmldsa_key_id = tkey:?digest=7c75714\n"
            )
            with open(inifile, "w") as f:
                f.write(config_with_tkey)

            user = User(inifile, data_path=statefile)
            mock_signer = unittest.mock.MagicMock()
            mock_from_uri.return_value = mock_signer

            signer = user.get_signer(ML_DSA_KEY)
            self.assertIs(signer, mock_signer)
            mock_from_uri.assert_called_once()
            mock_import.assert_not_called()

            # 2. Test recovery without configured URI
            mock_from_uri.reset_mock()
            mock_import.reset_mock()
            with open(inifile, "w") as f:
                f.write(REQUIRED_AND_SIGNING_KEYS)  # No ML-DSA key configured

            # 2a. Successful recovery -> writes to machine state file
            mock_import.return_value = ("tkey:?digest=7c75714", ML_DSA_KEY)
            mock_prompt.return_value = ""  # Default empty passphrase

            user_no_tkey = User(inifile, data_path=statefile)
            signer = user_no_tkey.get_signer(ML_DSA_KEY)
            self.assertIs(signer, mock_signer)
            mock_import.assert_called_once_with(passphrase=None)
            mock_from_uri.assert_called_once()
            self.assertEqual(
                user_no_tkey._app_data["signing-keys"][ML_DSA_KEY.keyid],
                "tkey:?digest=7c75714",
            )

            # verify it was written to state file
            user_reloaded = User(inifile, data_path=statefile)
            self.assertEqual(
                user_reloaded._app_data["signing-keys"][ML_DSA_KEY.keyid],
                "tkey:?digest=7c75714",
            )

            # 2b. Key mismatch during recovery -> raises RuntimeError
            with open(inifile, "w") as f:
                f.write(REQUIRED_AND_SIGNING_KEYS)
            user_mismatch = User(inifile, data_path=os.path.join(tempdir, "state2.ini"))
            other_key = SSlibKey(
                "other_key_id",
                "ml-dsa",
                "ml-dsa-44/1",
                {"public": "different_public_key"},
            )
            mock_import.return_value = ("tkey:?digest=7c75714", other_key)
            with self.assertRaises(RuntimeError):
                user_mismatch.get_signer(ML_DSA_KEY)

            # 2c. Import failure during recovery -> raises ClickException
            mock_import.side_effect = Exception("Device communication error")
            with self.assertRaises(click.ClickException):
                user_mismatch.get_signer(ML_DSA_KEY)

    def test_save_signing_key_uri(self):
        with TemporaryDirectory() as tempdir:
            inifile = os.path.join(tempdir, ".tuf-on-ci-sign.ini")
            statefile = os.path.join(tempdir, "signing-keys.ini")
            with open(inifile, "w") as f:
                f.write(WITH_PYKCS11LIB)

            user = User(inifile, data_path=statefile)
            self.assertEqual(dict(user._app_data["signing-keys"]), {})

            user.save_signing_key_uri("some_key_id", "some_uri")
            self.assertEqual(user._app_data["signing-keys"]["some_key_id"], "some_uri")

            # reload user to verify it was written to state file
            user2 = User(inifile, data_path=statefile)
            self.assertEqual(user2._app_data["signing-keys"]["some_key_id"], "some_uri")

            # verify local .tuf-on-ci-sign.ini was not modified
            with open(inifile) as f:
                self.assertEqual(f.read(), WITH_PYKCS11LIB)

    @unittest.mock.patch("securesystemslib.signer.Signer.from_priv_key_uri")
    def test_hierarchy_precedence(self, mock_from_uri):
        with TemporaryDirectory() as tempdir:
            inifile = os.path.join(tempdir, ".tuf-on-ci-sign.ini")
            statefile = os.path.join(tempdir, "signing-keys.ini")

            # Set repo config with a specific URI
            repo_config = (
                REQUIRED_AND_SIGNING_KEYS
                + "\n64eeece964e09c058ef8f9805daca546b01ba4719c80b6fe911b091a7c05124b = hsm:1?label=RepoOverride\n"
            )
            with open(inifile, "w") as f:
                f.write(repo_config)

            # Set state file with a different URI for the same key
            state_config = (
                "[signing-keys]\n"
                "64eeece964e09c058ef8f9805daca546b01ba4719c80b6fe911b091a7c05124b = hsm:2?label=MachineState\n"
            )
            with open(statefile, "w") as f:
                f.write(state_config)

            user = User(inifile, data_path=statefile)
            user.get_signer(NONCONFIGURED_KEY)

            # Local repo config must take precedence over machine state
            mock_from_uri.assert_called_once_with(
                "hsm:1?label=RepoOverride", NONCONFIGURED_KEY, unittest.mock.ANY
            )


if __name__ == "__main__":
    unittest.main()
