import os
import platform
import unittest
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
            with open(inifile, "w") as f:
                f.write(REQUIRED_AND_SIGNING_KEYS)

            user = User(inifile)
            # We should get a signer for the configured HSM
            hsm_signer = user.get_signer(HSM_KEY)
            self.assertIsInstance(hsm_signer, HSMSigner)
            self.assertEqual(
                hsm_signer.token_filter, {"label": "YubiKey PIV #15835999"}
            )
            self.assertEqual(
                hsm_signer.public_key.keyid,
                "762cb22caca65de5e9b7b6baecb84ca989d337280ce6914b6440aea95769ad93",
            )

            # Cache the signer
            user.set_signer(HSM_KEY, hsm_signer)

            # If the signing key is not configured, we expect a generic HSM signer
            other_signer = user.get_signer(NONCONFIGURED_KEY)
            self.assertIsInstance(other_signer, HSMSigner)
            self.assertEqual(other_signer.token_filter, {})
            self.assertEqual(
                other_signer.public_key.keyid,
                "64eeece964e09c058ef8f9805daca546b01ba4719c80b6fe911b091a7c05124b",
            )

            # another lookup should return same instance
            second_hsm_signer = user.get_signer(HSM_KEY)
            self.assertIs(hsm_signer, second_hsm_signer)


if __name__ == "__main__":
    unittest.main()
