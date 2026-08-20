import logging
import os
import platform
import sys
import tempfile
from configparser import ConfigParser

import click
from securesystemslib.signer import Key, Signer, TKeySigner

logger = logging.getLogger(__name__)

# some known locations where we might find libykcs11.
# These should all be _system_ locations (not user writable)
LIBYKCS11_LOCATIONS = {
    "Linux": [
        "/usr/lib/x86_64-linux-gnu/libykcs11.so",
        "/usr/lib64/libykcs11.so",
        "/usr/local/lib/libykcs11.so",
    ],
    "Darwin": ["/opt/homebrew/lib/libykcs11.dylib", "/usr/local/lib/libykcs11.dylib"],
}


def bold(text: str) -> str:
    return click.style(text, bold=True)


class User:
    """Class that manages user configuration and manages the users signer cache"""

    def __init__(self, path: str):
        self._config_path = path

        self._config = ConfigParser(interpolation=None)
        self._config.read(path)

        # TODO: create config if missing, ask/confirm values from user
        if not self._config:
            raise click.ClickException(f"Settings file {path} not found")
        try:
            self.name = self._config["settings"]["user-name"].lower()
            if not self.name.startswith("@"):
                self.name = f"@{self.name}"
            self.push_remote = self._config["settings"]["push-remote"]
            self.pull_remote = self._config["settings"]["pull-remote"]
        except KeyError as e:
            raise click.ClickException(
                f"Failed to find required setting {e} in {path}"
            ) from e

        # signing key config is not required
        if "signing-keys" in self._config:
            self._signing_key_uris = dict(self._config.items("signing-keys"))
        else:
            self._signing_key_uris = {}

        # probe for pykcs11lib if it's not set
        try:
            self.pykcs11lib = self._config["settings"]["pykcs11lib"]
        except KeyError:
            for loc in LIBYKCS11_LOCATIONS.get(platform.system(), []):
                if os.path.exists(loc):
                    self.pykcs11lib = loc
                    logger.debug("Using probed YKCS11 location %s", self.pykcs11lib)
                    break
            else:
                raise click.ClickException("Failed to find libykcs11")

        # signer cache gets populated as they are used the first time
        self._signers: dict[str, Signer] = {}

    def get_signer(self, key: Key) -> Signer:
        """Returns a Signer for the given public key

        The signer sources are (in order):
        * signers cached via set_signer()
        * any configured signer from 'signing-keys' config section
        * for ml-dsa keys without config, we assume TKey and attempt re-config
        * for sigstore type keys, a Signer is automatically created
        * for any remaining keys, HSM is assumed and a signer is created
        """

        def get_secret(secret: str) -> str:
            msg = f"Enter {secret} to sign (provide touch/bio authentication if needed)"

            # special case for tests -- prompt() will lockup trying to hide STDIN:
            if not sys.stdin.isatty():
                return sys.stdin.readline().rstrip()
            return click.prompt(bold(msg), hide_input=True)

        if key.keyid in self._signers:
            return self._signers[key.keyid]
        if key.keyid in self._signing_key_uris:
            # signer is not cached yet, but config exists
            uri = self._signing_key_uris[key.keyid]
            return Signer.from_priv_key_uri(uri, key, get_secret)

        if key.keytype == "ml-dsa":
            click.echo(
                f"No TKey configuration found for key {key.keyid}. Attempting to "
                "recreate configuration..."
            )
            click.prompt(
                bold("Please insert your Tillitis TKey and press enter"),
                default=True,
                show_default=False,
            )
            passphrase = click.prompt(
                bold("Enter TKey passphrase (press Enter for none)"),
                hide_input=True,
                default="",
                show_default=False,
            )
            if passphrase == "":
                passphrase = None
            try:
                uri, imported_key = TKeySigner.import_(passphrase=passphrase)
            except Exception as e:
                raise click.ClickException(f"Failed to read TKey: {e}") from e

            if imported_key.keyval != key.keyval:
                raise RuntimeError(
                    "TKey configuration failed, public key does not match:"
                    "This can mean incorrect passphrase or the need to configure"
                    "an older TKey device binary hash."
                )
        else:
            # backwards compatibility for users without keys in config file:
            # assume anything that is not signed with sigstore is signed with HSM
            if key.keytype == "sigstore-oidc":
                uri = "sigstore:?ambient=false"
            else:
                uri = "hsm:"

        signer = Signer.from_priv_key_uri(uri, key, get_secret)
        self.save_signing_key_uri(key.keyid, uri)
        return signer

    def set_signer(self, key: Key, signer: Signer) -> None:
        """Cache a signer for a keyid

        This should be called after a successful signing operation
        """
        self._signers[key.keyid] = signer

    def save_signing_key_uri(self, keyid: str, uri: str) -> None:
        """Save a signing key URI to the user configuration file."""
        if "signing-keys" not in self._config:
            self._config["signing-keys"] = {}
        self._config["signing-keys"][keyid] = uri

        config_dir = os.path.dirname(os.path.abspath(self._config_path))
        try:
            with tempfile.NamedTemporaryFile(
                "w", dir=config_dir, delete=False
            ) as temp_file:
                temp_path = temp_file.name
                self._config.write(temp_file)
                temp_file.flush()
                if os.path.exists(self._config_path):
                    mode = os.stat(self._config_path).st_mode
                    os.chmod(temp_path, mode)
            os.replace(temp_path, self._config_path)
        except Exception:
            if "temp_path" in locals() and os.path.exists(temp_path):
                os.remove(temp_path)
            raise

        # Update in-memory cache
        self._signing_key_uris[keyid] = uri
