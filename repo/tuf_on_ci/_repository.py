import json
import logging
import os
from shlex import join
import shutil

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum, unique
from glob import glob

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
    Key,
    Metadata,
    MetaFile,
    Root,
    Snapshot,
    TargetFile,
    Targets,
    Timestamp,
)
from tuf.api.serialization.json import CanonicalJSONSerializer, JSONSerializer
from tuf.repository import AbortEdit, Repository

# sigstore is not a supported key by default
KEY_FOR_TYPE_AND_SCHEME[("sigstore-oidc", "Fulcio")] = SigstoreKey
SIGNER_FOR_URI_SCHEME[SigstoreSigner.SCHEME] = SigstoreSigner

# TODO Add a metadata cache so we don't constantly open files
# TODO; Signing status probably should include an error message when valid=False

logger = logging.getLogger(__name__)


@unique
class State(Enum):
    ADDED = (0,)
    MODIFIED = (1,)
    REMOVED = (2,)


@dataclass
class TargetState:
    target: TargetFile
    state: State

    def __str__(self):
        return f"{self.target.path}: {self.state.name}"


@dataclass
class SigningStatus:
    invites: set[str]  # invites to _delegations_ of the role
    signed: set[str]
    missing: set[str]
    threshold: int
    target_changes: list[TargetState]
    valid: bool
    message: str | None


class SigningEventState:
    """Class to manage the .signing-event-state file"""

    def __init__(self, file_path: str):
        self._file_path = file_path
        self._invites: dict[str, list[str]] = {}
        if os.path.exists(file_path):
            with open(file_path) as f:
                data = json.load(f)
                self._invites = data["invites"]

    def invited_signers_for_role(self, rolename: str) -> list[str]:
        signers = []
        for invited_signer, invited_rolenames in self._invites.items():
            if rolename in invited_rolenames:
                signers.append(invited_signer)
        return signers

    def roles_with_delegation_invites(self) -> set[str]:
        roles = set()
        for invitee_roles in self._invites.values():
            for role in invitee_roles:
                if role in ["root", "targets"]:
                    roles.add("root")
                else:
                    roles.add("targets")
        return roles


class CIRepository(Repository):
    """A online repository implementation for use in GitHub Actions

    Arguments:
        dir: metadata directory to operate on
        prev_dir: optional known good repository directory
    """

    def __init__(self, dir: str, prev_dir: str | None = None):
        self._dir = dir
        self._prev_dir = prev_dir

        # read signing event state file
        self.state = SigningEventState(os.path.join(self._dir, ".signing-event-state"))

    def _get_filename(self, role: str) -> str:
        return f"{self._dir}/{role}.json"

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

        r = delegator.get_delegated_role(role)
        keys = []
        for keyid in r.keyids:
            try:
                key = delegator.get_key(keyid)
                if known_good and "x-tuf-on-ci-keyowner" not in key.unrecognized_fields:
                    # this is allowed for repo import case: we cannot identify known
                    # good keys and have to trust that delegations have not changed
                    continue

                keys.append(key)
            except ValueError:
                pass
        return keys

    def open(self, role: str) -> Metadata:
        """Return existing metadata, or create new metadata

        This is an implementation of Repository.open()
        """
        fname = self._get_filename(role)

        if not os.path.exists(fname):
            if role not in ["timestamp", "snapshot"]:
                raise ValueError(f"Cannot create new {role} metadata")
            if role == "timestamp":
                md: Metadata = Metadata(Timestamp())
                # workaround https://github.com/theupdateframework/python-tuf/issues/2307
                md.signed.snapshot_meta.version = 0
            else:
                md = Metadata(Snapshot())
                # workaround https://github.com/theupdateframework/python-tuf/issues/2307
                md.signed.meta.clear()
            # this makes version bumping in close() simpler
            md.signed.version = 0
        else:
            with open(fname, "rb") as f:
                md = Metadata.from_bytes(f.read())

        return md

    def signing_expiry_period(self, rolename: str) -> tuple[int, int]:
        """Extracts the signing and expiry period for a role

        If no signing expiry is configured, half the expiry period is used.
        """
        if rolename in ["timestamp", "snapshot"]:
            role = self.root().get_delegated_role(rolename)
            expiry_days = role.unrecognized_fields["x-tuf-on-ci-expiry-period"]
            signing_days = role.unrecognized_fields.get("x-tuf-on-ci-signing-period")
        else:
            signed = self.root() if rolename == "root" else self.targets(rolename)
            expiry_days = signed.unrecognized_fields["x-tuf-on-ci-expiry-period"]
            signing_days = signed.unrecognized_fields.get("x-tuf-on-ci-signing-period")

        if signing_days is None:
            signing_days = expiry_days // 2

        return (signing_days, expiry_days)

    def close(self, rolename: str, md: Metadata) -> None:
        """Write metadata to a file in repo dir

        Implementation of Repository.close(). Signs online roles.
        """
        md.signed.version += 1

        _, expiry_days = self.signing_expiry_period(rolename)

        md.signed.expires = datetime.utcnow() + timedelta(days=expiry_days)

        md.signatures.clear()
        for key in self._get_keys(rolename):
            if rolename in ["timestamp", "snapshot"]:
                uri = key.unrecognized_fields["x-tuf-on-ci-online-uri"]
                signer = Signer.from_priv_key_uri(uri, key)
                md.sign(signer, True)
            else:
                # offline signer, add empty sig
                md.signatures[key.keyid] = Signature(key.keyid, "")

        if rolename in ["timestamp", "snapshot"]:
            root_md: Metadata[Root] = self.open("root")
            # repository should never write unsigned online roles
            root_md.verify_delegate(rolename, md)

        filename = self._get_filename(rolename)
        data = md.to_bytes(JSONSerializer())
        with open(filename, "wb") as f:
            f.write(data)

    @property
    def targets_infos(self) -> dict[str, MetaFile]:
        """Implementation of Repository.target_infos

        Called by snapshot() when it needs current targets versions
        """
        # Note that this ends up loading every targets metadata. This could be
        # avoided if this data was produced in the signing event (as then we
        # know which targets metadata changed). Snapshot itself should not be
        # done before the signing event PR is reviewed though as the online keys
        # are then exposed
        targets_files: dict[str, MetaFile] = {}

        targets = self.targets()
        targets_files["targets.json"] = MetaFile(targets.version)
        if targets.delegations and targets.delegations.roles:
            for role in targets.delegations.roles.values():
                version = self.targets(role.name).version
                targets_files[f"{role.name}.json"] = MetaFile(version)

        return targets_files

    @property
    def snapshot_info(self) -> MetaFile:
        """Implementation of Repository.snapshot_info

        Called by timestamp() when it needs current snapshot version
        """
        return MetaFile(self.snapshot().version)

    def open_prev(self, role: str) -> Metadata | None:
        """Return known good metadata for role (if it exists)"""
        prev_fname = f"{self._prev_dir}/{role}.json"
        if os.path.exists(prev_fname):
            with open(prev_fname, "rb") as f:
                return Metadata.from_bytes(f.read())

        return None

    def _validate_role(
        self, delegator: Metadata, rolename: str
    ) -> tuple[bool, str | None]:
        """Validate role compatibility with this repository

        Returns bool for validity and optional error message"""
        md = self.open(rolename)
        prev_md = self.open_prev(rolename)

        # TODO: Current checks are more examples than actual checks

        # Make sure version grows if there are actual payload changes
        if (
            prev_md
            and prev_md.signed != md.signed
            and md.signed.version <= prev_md.signed.version
        ):
            return False, f"Version {md.signed.version} is not valid for {rolename}"

        days = md.signed.unrecognized_fields["x-tuf-on-ci-expiry-period"]
        if md.signed.expires > datetime.utcnow() + timedelta(days=days):
            return False, f"Expiry date is further than expected {days} days ahead"

        if isinstance(md.signed, Root):
            # tuf-on-ci is always consistent_snapshot
            if not md.signed.consistent_snapshot:
                return False, "Consistent snapshot is not enabled"

            # Specification: root version must be x+1, not just larger
            if (
                prev_md
                and prev_md.signed != md.signed
                and md.signed.version != prev_md.signed.version + 1
            ):
                return False, f"Version {md.signed.version} is not valid for root"

            # tuf-on-ci online signer must be the same for both roles
            ts_role = md.signed.get_delegated_role(Timestamp.type)
            sn_role = md.signed.get_delegated_role(Snapshot.type)
            if (
                ts_role.keyids != sn_role.keyids
                or ts_role.threshold != sn_role.threshold
            ):
                return False, "Timestamp and Snapshot signers differ"

            # Check expiry and signing period sanity
            for role in [ts_role, sn_role]:
                expiry_days = role.unrecognized_fields["x-tuf-on-ci-expiry-period"]
                signing_days = role.unrecognized_fields["x-tuf-on-ci-signing-period"]
                if signing_days < 1 or expiry_days <= signing_days:
                    return False, "Online signing or expiry period failed sanity check"

        # TODO for root:
        # * check delegations are correct

        # TODO for top-level targets:
        # * check delegations are expected
        # * check that target files in metadata match the files in targets/

        # TODO for delegated targets:
        # * check there are no delegations
        # * check that target files in metadata match the files in targets/

        try:
            delegator.verify_delegate(rolename, md)
        except UnsignedMetadataError:
            return False, None

        return True, None

    def _build_targets(self, target_dir: str, rolename: str) -> dict[str, TargetFile]:
        """Build a roles dict of TargetFile based on target files in a directory"""
        targetfiles = {}

        patterns = ["*"]

        if rolename != "targets":
            delegations = self.targets("targets").delegations
            if delegations and delegations.roles and rolename in delegations.roles:
                    paths = delegations.roles[rolename].paths
                    if paths:
                        patterns = paths

        for pattern in patterns:
            for fname in glob(pattern, root_dir=target_dir):
                realpath = os.path.join(target_dir, fname)
                if not os.path.isfile(realpath):
                    continue

                # fname is a URL path, not OS path
                targetfiles[fname] = TargetFile.from_file(
                    fname, realpath, ["sha256"]
                )
        return targetfiles

    def _known_good_root(self) -> Root:
        """Return the Root object from the known-good repository state"""
        assert self._prev_dir is not None
        prev_path = os.path.join(self._prev_dir, "root.json")
        if os.path.exists(prev_path):
            with open(prev_path, "rb") as f:
                md = Metadata.from_bytes(f.read())
            assert isinstance(md.signed, Root)
            return md.signed

        # this role did not exist: return an empty one for comparison purposes
        return Root()

    def _known_good_targets(self, rolename: str) -> Targets:
        """Return Targets from the known good version (signing event start point)"""
        assert self._prev_dir
        prev_path = os.path.join(self._prev_dir, f"{rolename}.json")
        if os.path.exists(prev_path):
            with open(prev_path, "rb") as f:
                md = Metadata.from_bytes(f.read())
            assert isinstance(md.signed, Targets)
            return md.signed

        # this role did not exist: return an empty one for comparison purposes
        return Targets()

    def _get_target_changes(self, rolename: str) -> list[TargetState]:
        """Compare targetfiles in known good version and signing event version:
        return list of changes"""

        if rolename in ["root", "timestamp", "snapshot"]:
            return []

        changes = []

        known_good_targetfiles = self._known_good_targets(rolename).targets
        for targetfile in self.targets(rolename).targets.values():
            if targetfile.path not in known_good_targetfiles:
                # new in signing event
                changes.append(TargetState(targetfile, State.ADDED))
            elif targetfile != known_good_targetfiles[targetfile.path]:
                # changed in signing event
                changes.append(TargetState(targetfile, State.MODIFIED))
                del known_good_targetfiles[targetfile.path]
            else:
                # no changes in signing event
                del known_good_targetfiles[targetfile.path]

        for targetfile in known_good_targetfiles.values():
            changes.append(TargetState(targetfile, State.REMOVED))

        return changes

    def _get_signing_status(
        self, rolename: str, known_good: bool
    ) -> SigningStatus | None:
        """Build signing status for role.

        This method relies on event state (.signing-event-state) to be accurate.
        Returns None only when known_good is True, and then in two cases: if delegating
        role is not root (because then the known good state is irrelevant) and also if
        there is no known good version yet.
        """
        invites = set()
        sigs = set()
        missing_sigs = set()
        md = self.open(rolename)

        # Find delegating metadata. For root handle the special case of known good
        # delegating metadata.
        if known_good:
            delegator = None
            if rolename == "root":
                delegator = self.open_prev("root")
            if not delegator:
                # Not root role or there is no known-good root metadata yet
                return None
        elif rolename in ["root", "targets"]:
            delegator = self.open("root")
        else:
            delegator = self.open("targets")

        # Build list of invites to all delegated roles of rolename
        delegation_names = []
        if rolename == "root":
            delegation_names = ["root", "targets"]
        elif rolename == "targets" and md.signed.delegations:
            delegation_names = md.signed.delegations.roles.keys()
        for delegation_name in delegation_names:
            invites.update(self.state.invited_signers_for_role(delegation_name))

        role = delegator.signed.get_delegated_role(rolename)

        # Build lists of signed signers and not signed signers
        for key in self._get_keys(rolename, known_good):
            keyowner = key.unrecognized_fields["x-tuf-on-ci-keyowner"]
            try:
                payload = CanonicalJSONSerializer().serialize(md.signed)
                key.verify_signature(md.signatures[key.keyid], payload)
                sigs.add(keyowner)
            except (KeyError, UnverifiedSignatureError):
                missing_sigs.add(keyowner)

        # Document changes to targets metadata in this signing event
        target_changes = self._get_target_changes(rolename)

        # Just to be sure: double check that delegation threshold is reached
        if invites:
            valid, msg = False, None
        else:
            valid, msg = self._validate_role(delegator, rolename)

        return SigningStatus(
            invites, sigs, missing_sigs, role.threshold, target_changes, valid, msg
        )

    def status(self, rolename: str) -> tuple[SigningStatus, SigningStatus | None]:
        """Returns signing status for role.

        In case of root, another SigningStatus may be returned for the previous
        'known good' root.
        Uses .signing-event-state file."""
        if rolename in ["timestamp", "snapshot"]:
            raise ValueError("Not supported for online metadata")

        known_good_status = self._get_signing_status(rolename, known_good=True)
        signing_event_status = self._get_signing_status(rolename, known_good=False)
        assert signing_event_status is not None

        return signing_event_status, known_good_status

    def build(self, metadata_path: str, artifact_path: str | None):
        """Build a publishable directory of metadata and (optionally) artifacts"""
        os.makedirs(metadata_path, exist_ok=True)
        if artifact_path:
            os.makedirs(artifact_path, exist_ok=True)

        for src_path in glob(os.path.join(self._dir, "root_history", "*.root.json")):
            shutil.copy(src_path, metadata_path)
        shutil.copy(os.path.join(self._dir, "timestamp.json"), metadata_path)

        snapshot = self.snapshot()
        dst_path = os.path.join(metadata_path, f"{snapshot.version}.snapshot.json")
        shutil.copy(os.path.join(self._dir, "snapshot.json"), dst_path)

        for filename, metafile in snapshot.meta.items():
            src_path = os.path.join(self._dir, filename)
            dst_path = os.path.join(metadata_path, f"{metafile.version}.{filename}")
            shutil.copy(src_path, dst_path)

            if artifact_path:
                targets = self.targets(filename[: -len(".json")])
                for target in targets.targets.values():
                    role, sep, name = target.path.rpartition("/")
                    os.makedirs(os.path.join(artifact_path, role), exist_ok=True)
                    src_path = os.path.join(self._dir, "..", "targets", role, name)
                    for hash in target.hashes.values():
                        dst_path = os.path.join(artifact_path, role, f"{hash}.{name}")
                        shutil.copy(src_path, dst_path)

    def bump_expiring(self, rolename: str) -> int | None:
        """Create a new version of role if it is about to expire"""
        now = datetime.utcnow()
        bumped = True

        with self.edit(rolename) as signed:
            signing_days, _ = self.signing_expiry_period(rolename)
            delta = timedelta(days=signing_days)

            logger.debug(f"{rolename} signing period starts {signed.expires - delta}")
            if now + delta < signed.expires:
                # no need to bump version
                bumped = False
                raise AbortEdit

        return signed.version if bumped else None

    def update_targets(self, rolename: str) -> bool:
        if rolename in ["root", "timestamp", "snapshot"]:
            return False

        new_tfiles = self._build_targets(
            os.path.join(self._dir, "..", "targets"), rolename
        )
        with self.edit_targets(rolename) as targets:
            # Keep any existing custom fields
            for path, tfile in targets.targets.items():
                if path in new_tfiles:
                    new_tfiles[path].unrecognized_fields = tfile.unrecognized_fields

            # if targets dict has no changes, cancel the metadata edit
            if targets.targets == new_tfiles:
                raise AbortEdit("No target changes needed")

            targets.targets = new_tfiles
            return True

    def is_signed(self, rolename: str) -> bool:
        """Return True if role is correctly signed and not in signing period

        NOTE: a role in signing period is valid for TUF clients but this method returns
        false in this case: this is useful when repository decides if it needs a new
        online role version.
        """
        role_md = self.open(rolename)
        if rolename in ["root", "timestamp", "snapshot", "targets"]:
            delegator = self.open("root")
        else:
            delegator = self.open("targets")
        try:
            delegator.verify_delegate(rolename, role_md)
        except UnsignedMetadataError:
            return False

        signing_days, _ = self.signing_expiry_period(rolename)
        delta = timedelta(days=signing_days)

        return datetime.utcnow() + delta < role_md.signed.expires
