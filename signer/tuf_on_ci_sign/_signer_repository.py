# Copyright 2023 Google LLC

"""Internal repository module for TUF-on-CI signer tools"""

import filecmp
import json
import logging
import os
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum, unique
from glob import glob

import click
from securesystemslib.exceptions import UnverifiedSignatureError
from securesystemslib.signer import (
    KEY_FOR_TYPE_AND_SCHEME,
    SIGNER_FOR_URI_SCHEME,
    Signature,
    Signer,
    SigstoreKey,
    SigstoreSigner,
)
from tuf.api.exceptions import UnsignedMetadataError
from tuf.api.metadata import (
    DelegatedRole,
    Delegations,
    Key,
    Metadata,
    Role,
    Root,
    Signed,
    Targets,
)
from tuf.api.serialization.json import CanonicalJSONSerializer, JSONSerializer
from tuf.repository import AbortEdit, Repository

from tuf_on_ci_sign._user import User

logger = logging.getLogger(__name__)

# Enable experimental sigstore keys
KEY_FOR_TYPE_AND_SCHEME[("sigstore-oidc", "Fulcio")] = SigstoreKey
SIGNER_FOR_URI_SCHEME[SigstoreSigner.SCHEME] = SigstoreSigner


@unique
class SignerState(Enum):
    NO_ACTION = (0,)
    UNINITIALIZED = (1,)
    INVITED = (2,)
    SIGNATURE_NEEDED = (4,)


@dataclass
class OnlineConfig:
    # key is used as signing key for both snapshot and timestamp
    key: Key
    timestamp_expiry: int
    timestamp_signing: int
    snapshot_expiry: int
    snapshot_signing: int


@dataclass
class OfflineConfig:
    signers: list[str]
    threshold: int
    expiry_period: int
    signing_period: int


def blue(text: str) -> str:
    return click.style(text, fg="bright_blue")


def _find_changed_roles(known_good_dir: str, signing_event_dir: str) -> list[str]:
    """Return list of roles that exist and have changed in this signing event"""
    files = glob("*.json", root_dir=signing_event_dir)
    changed_roles = []
    for fname in files:
        if not os.path.exists(f"{known_good_dir}/{fname}") or not filecmp.cmp(
            f"{signing_event_dir}/{fname}", f"{known_good_dir}/{fname}", shallow=False
        ):
            if fname in ["timestamp.json", "snapshot.json"]:
                raise RuntimeError("Unexpected change in online files")

            changed_roles.append(fname[: -len(".json")])

    # reorder, toplevels first
    for toplevel in ["targets", "root"]:
        if toplevel in changed_roles:
            changed_roles.remove(toplevel)
            changed_roles.insert(0, toplevel)

    return changed_roles


class SignerRepository(Repository):
    """A repository implementation for the signer tool"""

    def __init__(
        self,
        dir: str,
        prev_dir: str,
        user: User,
    ):
        self.user = user
        self._dir = dir
        self._prev_dir = prev_dir
        self._invites: dict[str, list[str]] = {}
        self._signers: dict[str, Signer] = {}

        # read signing event state file (invites)
        state_file = os.path.join(self._dir, ".signing-event-state")
        if os.path.exists(state_file):
            with open(state_file) as f:
                config = json.load(f)
            self._invites = config["invites"]

        # Figure out needed signatures
        self.unsigned = set()
        for rolename in _find_changed_roles(self._prev_dir, self._dir):
            if self._user_signature_needed(rolename) and rolename not in self.invites:
                self.unsigned.add(rolename)

        # Find current state
        if not os.path.exists(os.path.join(self._dir, "root.json")):
            self.state = SignerState.UNINITIALIZED
        elif self.invites:
            self.state = SignerState.INVITED
        elif self.unsigned:
            self.state = SignerState.SIGNATURE_NEEDED
        else:
            self.state = SignerState.NO_ACTION

    @property
    def invites(self) -> list[str]:
        """Return the list of roles the user has been invited to"""
        try:
            return self._invites[self.user.name]
        except KeyError:
            return []

    def _user_signature_needed(self, rolename: str) -> bool:
        """Return true if current role metadata is unsigned by user"""
        md = self.open(rolename)
        for key in self._get_keys(rolename):
            keyowner = key.unrecognized_fields["x-tuf-on-ci-keyowner"]
            if keyowner == self.user.name:
                try:
                    payload = CanonicalJSONSerializer().serialize(md.signed)
                    key.verify_signature(md.signatures[key.keyid], payload)
                except (KeyError, UnverifiedSignatureError):
                    return True

        # Root signers for previous root version are eligible to sign
        # the current version
        if rolename == "root":
            for key in self._get_keys(rolename, True):
                keyowner = key.unrecognized_fields["x-tuf-on-ci-keyowner"]
                if keyowner == self.user.name:
                    try:
                        payload = CanonicalJSONSerializer().serialize(md.signed)
                        key.verify_signature(md.signatures[key.keyid], payload)
                    except (KeyError, UnverifiedSignatureError):
                        return True

        return False

    def _get_filename(self, role: str) -> str:
        return os.path.join(self._dir, f"{role}.json")

    def _get_versioned_root_filename(self, version: int) -> str:
        return os.path.join(self._dir, "root_history", f"{version}.root.json")

    def _known_good_version(self, rolename: str) -> int:
        """Return the version of `rolename` in the known-good repository state"""
        prev_path = os.path.join(self._prev_dir, f"{rolename}.json")
        if os.path.exists(prev_path):
            with open(prev_path, "rb") as f:
                md = Metadata.from_bytes(f.read())
            return md.signed.version

        return 0

    def _known_good_root(self) -> Root:
        """Return the Root object from the known-good repository state"""
        prev_path = os.path.join(self._prev_dir, "root.json")
        if os.path.exists(prev_path):
            with open(prev_path, "rb") as f:
                md = Metadata.from_bytes(f.read())
            assert isinstance(md.signed, Root)
            return md.signed

        # this role did not exist: return an empty one for comparison purposes
        return Root()

    def _known_good_targets(self, rolename: str) -> Targets:
        """Return a Targets object from the known-good repository state"""
        prev_path = os.path.join(self._prev_dir, f"{rolename}.json")
        if os.path.exists(prev_path):
            with open(prev_path, "rb") as f:
                md = Metadata.from_bytes(f.read())
            assert isinstance(md.signed, Targets)
            return md.signed

        # this role did not exist: return an empty one for comparison purposes
        return Targets()

    def _get_keys(self, role: str, known_good: bool = False) -> list[Key]:
        """Return public keys for delegated role

        If known_good is True, use the keys defined in known good delegator.
        Otherwise use keys defined in the signing event delegator.
        """
        if role in ["root", "timestamp", "snapshot", "targets"]:
            if known_good:
                delegator: Root | Targets = self._known_good_root()
            else:
                delegator = self.root()
        else:
            if known_good:
                delegator = self._known_good_targets("targets")
            else:
                delegator = self.targets()

        keys = []
        try:
            r = delegator.get_delegated_role(role)
            for keyid in r.keyids:
                key = delegator.get_key(keyid)
                if known_good and "x-tuf-on-ci-keyowner" not in key.unrecognized_fields:
                    # this is allowed for repo import case: we cannot identify known
                    # good keys and have to trust that delegations have not changed
                    continue

                keys.append(key)
        except ValueError:
            pass  # role is not delegated or key was not found

        return keys

    def _sign(self, role: str, md: Metadata, key: Key) -> None:
        while True:
            signer = self.user.get_signer(key)
            try:
                sig = md.sign(signer, True)
                key.verify_signature(sig, md.signed_bytes)
                self.user.set_signer(key, signer)
                break
            except UnsignedMetadataError as e:
                print(f"Failed to sign {role} with {self.user.name} key.\n    {e}")
                logger.debug("Sign traceback", exc_info=True)
            except UnverifiedSignatureError as e:
                print(
                    f"Failed to verify {self.user.name} signature "
                    f"(is this the correct key?)\n    {e}"
                )
                logger.debug("Verify traceback", exc_info=True)

            click.prompt(
                "Press any key to try again (Ctrl-C to cancel)",
                default=True,
                show_default=False,
            )

    def _write(self, role: str, md: Metadata) -> None:
        filename = self._get_filename(role)

        os.makedirs(os.path.join(self._dir, "root_history"), exist_ok=True)

        data = md.to_bytes(JSONSerializer())
        with open(filename, "wb") as f:
            f.write(data)

        # For root, also store the versioned metadata
        if role == "root":
            with open(self._get_versioned_root_filename(md.signed.version), "wb") as f:
                f.write(data)

    def open(self, role: str) -> Metadata:
        """Read metadata from repository directory, or create new metadata"""
        fname = self._get_filename(role)

        if not os.path.exists(fname):
            if role in ["snapshot", "timestamp"]:
                raise ValueError(f"Cannot create {role}")
            if role == "root":
                md: Metadata = Metadata(Root())
            else:
                md = Metadata(Targets())
            md.signed.unrecognized_fields["x-tuf-on-ci-expiry-period"] = 0
            md.signed.unrecognized_fields["x-tuf-on-ci-signing-period"] = 0
        else:
            with open(fname, "rb") as f:
                md = Metadata.from_bytes(f.read())

        return md

    def close(self, role: str, md: Metadata) -> None:
        """Write metadata to a file in the repository directory

        Note that resulting metadata is not signed and all existing
        signatures are removed.
        """
        # Make sure version is bumped only once per signing event
        md.signed.version = self._known_good_version(role) + 1

        # Set expiry based on custom metadata
        days = md.signed.unrecognized_fields["x-tuf-on-ci-expiry-period"]
        md.signed.expires = datetime.utcnow() + timedelta(days=days)

        # figure out if there are open invites to delegations of this role
        open_invites = False
        delegated = self._get_delegated_rolenames(md)
        for invited_roles in self._invites.values():
            for invited_role in invited_roles:
                if invited_role in delegated:
                    open_invites = True
                    break

        if role == "root":
            # special case: root includes its own signing keys. We want
            # to handle both old root keys (from known good version) and
            # new keys from the root version we are storing
            keys = self._get_keys(role, True)

            assert isinstance(md.signed, Root)
            r = md.signed.get_delegated_role("root")
            for keyid in r.keyids:
                duplicate = False
                for key in keys:
                    if keyid == key.keyid:
                        duplicate = True
                if not duplicate:
                    keys.append(md.signed.get_key(keyid))
        else:
            # for all other roles we can use the keys defined in
            # signing event
            keys = self._get_keys(role)

        # wipe signatures, update "unsigned" list
        if role in self.unsigned:
            self.unsigned.remove(role)

        md.signatures.clear()
        for key in keys:
            md.signatures[key.keyid] = Signature(key.keyid, "")

            # Mark role as unsigned if user is a signer (and there are no open invites)
            keyowner = key.unrecognized_fields["x-tuf-on-ci-keyowner"]
            if keyowner == self.user.name and not open_invites:
                self.unsigned.add(role)

        self._write(role, md)

    @staticmethod
    def _get_delegated_rolenames(md: Metadata) -> list[str]:
        if isinstance(md.signed, Root):
            return list(md.signed.roles.keys())
        if (
            isinstance(md.signed, Targets)
            and md.signed.delegations
            and md.signed.delegations.roles
        ):
            return list(md.signed.delegations.roles.keys())
        return []

    def get_online_config(self) -> OnlineConfig:
        """Read configuration for online delegation from metadata"""
        root = self.root()

        timestamp_role = root.get_delegated_role("timestamp")
        snapshot_role = root.get_delegated_role("snapshot")
        timestamp_expiry = timestamp_role.unrecognized_fields[
            "x-tuf-on-ci-expiry-period"
        ]
        timestamp_signing = timestamp_role.unrecognized_fields.get(
            "x-tuf-on-ci-signing-period"
        )
        snapshot_expiry = snapshot_role.unrecognized_fields["x-tuf-on-ci-expiry-period"]
        snapshot_signing = snapshot_role.unrecognized_fields.get(
            "x-tuf-on-ci-signing-period"
        )

        if timestamp_signing is None:
            timestamp_signing = timestamp_expiry // 2
        if snapshot_signing is None:
            snapshot_signing = snapshot_expiry // 2

        keyid = timestamp_role.keyids[0]
        key = root.get_key(keyid)

        return OnlineConfig(
            key, timestamp_expiry, timestamp_signing, snapshot_expiry, snapshot_signing
        )

    def set_online_config(self, online_config: OnlineConfig):
        """Store online delegation configuration in metadata."""

        with self.edit_root() as root:
            timestamp = root.get_delegated_role("timestamp")
            snapshot = root.get_delegated_role("snapshot")

            # Remove current keys
            for keyid in timestamp.keyids.copy():
                root.revoke_key(keyid, "timestamp")
            for keyid in snapshot.keyids.copy():
                root.revoke_key(keyid, "snapshot")

            # Add new keys
            root.add_key(online_config.key, "timestamp")
            root.add_key(online_config.key, "snapshot")

            # set online role periods
            timestamp.unrecognized_fields["x-tuf-on-ci-expiry-period"] = (
                online_config.timestamp_expiry
            )
            timestamp.unrecognized_fields["x-tuf-on-ci-signing-period"] = (
                online_config.timestamp_signing
            )
            snapshot.unrecognized_fields["x-tuf-on-ci-expiry-period"] = (
                online_config.snapshot_expiry
            )
            snapshot.unrecognized_fields["x-tuf-on-ci-signing-period"] = (
                online_config.snapshot_signing
            )

    def get_role_config(self, rolename: str) -> OfflineConfig | None:
        """Read configuration for delegation and role from metadata"""
        if rolename in ["timestamp", "snapshot"]:
            raise ValueError("online roles not supported")

        if rolename == "root":
            delegator: Root | Targets = self.root()
            delegated: Root | Targets = delegator
        elif rolename == "targets":
            delegator = self.root()
            delegated = self.targets()
        else:
            delegator = self.targets()
            delegated = self.targets(rolename)

        try:
            role = delegator.get_delegated_role(rolename)
        except ValueError:
            return None

        expiry = delegated.unrecognized_fields["x-tuf-on-ci-expiry-period"]
        signing = delegated.unrecognized_fields["x-tuf-on-ci-signing-period"]
        threshold = role.threshold
        signers = []
        # Include current invitees on config
        for signer, rolenames in self._invites.items():
            if rolename in rolenames:
                signers.append(signer)
        # Include current signers on config
        for keyid in role.keyids:
            try:
                key = delegator.get_key(keyid)
                signers.append(key.unrecognized_fields["x-tuf-on-ci-keyowner"])
            except ValueError:
                pass

        return OfflineConfig(signers, threshold, expiry, signing)

    def set_role_config(
        self, rolename: str, config: OfflineConfig, signing_key: Key | None
    ):
        """Store delegation & role configuration in metadata.

        signing_key is only used if user is configured as signer"""
        if rolename in ["timestamp", "snapshot"]:
            raise ValueError("online roles not supported")

        # Remove invites for the role
        new_invites = {}
        for invited_signer, invited_roles in self._invites.items():
            if rolename in invited_roles:
                invited_roles.remove(rolename)
            if invited_roles:
                new_invites[invited_signer] = invited_roles
        self._invites = new_invites

        # Handle new invitations
        for signer in config.signers:
            # Does signer already have a key?
            is_signer = False
            for key in self._get_keys(rolename):
                if signer == key.unrecognized_fields["x-tuf-on-ci-keyowner"]:
                    is_signer = True

            # If signer does not have key, add invitation
            if not is_signer:
                if signer not in self._invites:
                    self._invites[signer] = []
                if rolename not in self._invites[signer]:
                    self._invites[signer].append(rolename)

        if rolename in ["root", "targets"]:
            delegator_cm: AbstractContextManager[Root | Targets] = self.edit_root()
        else:
            delegator_cm = self.edit_targets()

        with delegator_cm as delegator:
            changed = False
            try:
                role = delegator.get_delegated_role(rolename)
            except ValueError:
                # Role does not exist yet: create delegation
                assert isinstance(delegator, Targets)
                role = DelegatedRole(rolename, [], 1, True, [f"{rolename}/*"])
                if not delegator.delegations:
                    delegator.delegations = Delegations({}, {})
                assert delegator.delegations.roles is not None
                delegator.delegations.roles[rolename] = role
                changed = True

            keyids = role.keyids.copy()
            for keyid in keyids:
                key = delegator.get_key(keyid)
                key_owner = key.unrecognized_fields["x-tuf-on-ci-keyowner"]
                if key_owner in config.signers:
                    # signer is still a signer
                    config.signers.remove(
                        key.unrecognized_fields["x-tuf-on-ci-keyowner"]
                    )
                else:
                    # signer was removed
                    delegator.revoke_key(keyid, rolename)
                    changed = True

            # Add user themselves
            invited = (
                self.user.name in self._invites
                and rolename in self._invites[self.user.name]
            )
            if invited and signing_key:
                signing_key.unrecognized_fields["x-tuf-on-ci-keyowner"] = self.user.name
                delegator.add_key(signing_key, rolename)

                self._invites[self.user.name].remove(rolename)
                if not self._invites[self.user.name]:
                    del self._invites[self.user.name]

                # Add role to unsigned list even if the role itself does not change
                self.unsigned.add(rolename)

                changed = True

            if role.threshold != config.threshold:
                changed = True
            role.threshold = config.threshold
            if not changed:
                # Exit the edit-contextmanager without saving if no changes were done
                raise AbortEdit(f"No changes to delegator of {rolename}")

        # Modify the role itself
        with self.edit(rolename) as signed:
            expiry = signed.unrecognized_fields.get("x-tuf-on-ci-expiry-period")
            signing = signed.unrecognized_fields.get("x-tuf-on-ci-signing-period")
            if expiry == config.expiry_period and signing == config.signing_period:
                raise AbortEdit(f"No changes to {rolename}")

            signed.unrecognized_fields["x-tuf-on-ci-expiry-period"] = (
                config.expiry_period
            )
            signed.unrecognized_fields["x-tuf-on-ci-signing-period"] = (
                config.signing_period
            )

        state_file_path = os.path.join(self._dir, ".signing-event-state")
        if self._invites:
            with open(state_file_path, "w") as f:
                state_file = {"invites": self._invites}
                f.write(json.dumps(state_file, indent=2))
        elif os.path.exists(state_file_path):
            os.remove(state_file_path)

    def _role_status_lines(self, rolename: str) -> list[str]:
        # Handle a custom metadata: expiry and signing period
        output = []

        if rolename == "root":
            signed: Signed = self.root()
            old_signed: Signed = self._known_good_root()
        else:
            signed = self.targets(rolename)
            old_signed = self._known_good_targets(rolename)

        expiry = signed.unrecognized_fields["x-tuf-on-ci-expiry-period"]
        signing = signed.unrecognized_fields["x-tuf-on-ci-signing-period"]
        old_expiry = old_signed.unrecognized_fields.get("x-tuf-on-ci-expiry-period")
        old_signing = old_signed.unrecognized_fields.get("x-tuf-on-ci-signing-period")

        output.append(blue(f"{rolename} v{signed.version}"))

        if expiry != old_expiry or signing != old_signing:
            output.append(
                f" * Expiry period: {expiry} days, signing period: {signing} days"
            )
            if signed.version != 1:
                output.append(
                    f"   (expiry period was {old_expiry} days, "
                    f"signing period was {old_signing} days"
                )

        return output

    def _delegation_status_lines(self, rolename: str) -> list[str]:
        """Return information about delegation changes"""
        # NOTE key content changes are currently not noticed
        # (think keyid staying the same but public key bytes changing)

        def _get_signer_name(key: Key) -> str:
            if name in ["timestamp", "snapshot"]:
                # there's no "signer" in the online case: use signing system as signer
                uri = key.unrecognized_fields["x-tuf-on-ci-online-uri"]
                return uri.split(":")[0]
            return key.unrecognized_fields["x-tuf-on-ci-keyowner"]

        output = []
        delegations: dict[str, Role] = {}
        old_delegations: dict[str, Role] = {}

        # Find delegations for both signing event and known-good state
        if rolename == "root":
            root = self.root()
            delegations = dict(root.roles)

            old_root = self._known_good_root()
            # avoid using the default delegations for initial old_delegations
            if root.version > 1:
                old_delegations = dict(old_root.roles)

            # Use timestamp output for both snapshot and timestamp: NOTE: we should
            # validate that the delegations really are identical
            delegations.pop("snapshot")
            old_delegations.pop("snapshot", None)
        else:
            targets = self.targets(rolename)
            if targets.delegations and targets.delegations.roles:
                delegations = dict(targets.delegations.roles)

            old_targets = self._known_good_targets(rolename)
            if old_targets.delegations and old_targets.delegations.roles:
                old_delegations = dict(old_targets.delegations.roles)

        # Produce description of changes (New/Modified/Removed)
        for name, role in delegations.items():
            if name == "timestamp":
                title = "online delegations timestamp & snapshot"
            else:
                title = f"delegation {name}"

            signers = []
            for key in self._get_keys(name):
                signers.append(_get_signer_name(key))

            if name not in old_delegations:
                output.append(f" * New {title}")
                output.append(
                    f"   * Signers: {role.threshold}/{len(signers)} of {signers}"
                )
            else:
                old_role = old_delegations[name]
                old_signers = []
                for key in self._get_keys(name, known_good=True):
                    old_signers.append(_get_signer_name(key))

                if role != old_role:
                    output.append(f" * Modified {title}")
                    output.append(
                        f"   * Signers: {role.threshold}/{len(signers)} of {signers}"
                    )
                    output.append(
                        f"     (was: {old_role.threshold}/{len(old_signers)} "
                        f"of {old_signers}"
                    )
                del old_delegations[name]

        for name in old_delegations:
            output.append(f" * Removed {name}")

        return output

    def _artifact_status_lines(self, rolename: str) -> list[str]:
        if rolename == "root":
            return []

        output = []
        old_artifacts = self._known_good_targets(rolename).targets
        artifacts = self.targets(rolename).targets
        for artifact in artifacts.values():
            if artifact.path not in old_artifacts:
                output.append(f" * New artifact '{artifact.path}'")
            else:
                if artifact != old_artifacts[artifact.path]:
                    output.append(f" * Modified artifact '{artifact.path}'")
                del old_artifacts[artifact.path]
        for removed_artifact in old_artifacts.values():
            output.append(f" * Removed artifact '{removed_artifact.path}'")

        return output

    def status(self, rolename: str) -> str:
        if rolename in ["timestamp", "snapshot"]:
            raise ValueError("Cannot handle changes in online roles")

        output = [""]

        # TODO validate what we can: see issue #95

        output.extend(self._role_status_lines(rolename))
        output.extend(self._delegation_status_lines(rolename))
        output.extend(self._artifact_status_lines(rolename))

        return "\n".join(output)

    def sign(self, rolename: str):
        """Sign without payload changes"""
        md = self.open(rolename)
        for key in self._get_keys(rolename):
            keyowner = key.unrecognized_fields["x-tuf-on-ci-keyowner"]
            if keyowner == self.user.name:
                self._sign(rolename, md, key)
                self._write(rolename, md)
                return

        # Root is eligible to sign current root if the signer was valid
        # in previous version
        if rolename == "root":
            for key in self._get_keys(rolename, True):
                keyowner = key.unrecognized_fields["x-tuf-on-ci-keyowner"]
                if keyowner == self.user.name:
                    self._sign(rolename, md, key)
                    self._write(rolename, md)
                    return

        raise ValueError(f"{rolename} signing key for {self.user.name} not found")
