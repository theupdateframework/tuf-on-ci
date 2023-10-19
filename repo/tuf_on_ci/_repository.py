import json
import logging
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum, unique
from glob import glob

from securesystemslib.signer import (
    KEY_FOR_TYPE_AND_SCHEME,
    Signature,
    Signer,
    SigstoreKey,
    SigstoreSigner,
)
from sigstore.oidc import detect_credential
from tuf.api.exceptions import UnsignedMetadataError
from tuf.api.metadata import (
    Key,
    Metadata,
    MetaFile,
    Root,
    Signed,
    Snapshot,
    TargetFile,
    Targets,
    Timestamp,
    VerificationResult,
)
from tuf.api.serialization.json import JSONSerializer
from tuf.repository import AbortEdit, Repository

# sigstore is not a supported key by default
KEY_FOR_TYPE_AND_SCHEME[("sigstore-oidc", "Fulcio")] = SigstoreKey

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
class VerificationResultWithKeys:
    """Signature verification result for delegated role metadata.

    Attributes:
        verified: True, if threshold of signatures is met.
        signed: Signed delegated Keys.
        unsigned: Unsigned delegated Keys.

    """

    verified: bool
    signed: list[Key]
    unsigned: list[Key]

    @classmethod
    def from_verification_result(
        cls, original: VerificationResult, delegator: Root | Targets
    ):
        signed = [delegator.get_key(keyid) for keyid in original.signed]
        signed.sort(key=lambda key: key.keyid)
        unsigned = [delegator.get_key(keyid) for keyid in original.unsigned]
        unsigned.sort(key=lambda key: key.keyid)
        return VerificationResultWithKeys(original.verified, signed, unsigned)

    def __bool__(self) -> bool:
        return self.verified

    def union(
        self, other: "VerificationResultWithKeys"
    ) -> "VerificationResultWithKeys":
        """Combine two verification results.

        Can be used to verify if root metadata is signed by the threshold of
        keys of previous root and the threshold of keys of itself.
        """
        signed = self.signed.copy()
        signed.extend([s for s in other.signed if s not in signed])
        unsigned = self.unsigned.copy()
        unsigned.extend([s for s in other.unsigned if s not in unsigned])

        return VerificationResultWithKeys(
            self.verified and other.verified, signed, unsigned
        )


@dataclass
class SigningStatus:
    invites: set[str]  # invites to _delegations_ of the role
    verification_result: VerificationResultWithKeys
    target_changes: list[TargetState]
    valid: bool
    message: str | None


def _get_verification_result(
    delegator: Root | Targets, rolename: str, md: Metadata
) -> VerificationResultWithKeys:
    """Helper to get verification results with Keys instead of keyids"""
    result = delegator.get_verification_result(rolename, md.signed_bytes, md.signatures)
    return VerificationResultWithKeys.from_verification_result(result, delegator)


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
        unsigned = self._get_verification_result(rolename, md).unsigned
        for key in unsigned:
            if rolename in ["timestamp", "snapshot"]:
                uri = key.unrecognized_fields["x-tuf-on-ci-online-uri"]
                # WORKAROUND while sigstoresigner is not finished
                if uri == "sigstore:":
                    signer = SigstoreSigner(detect_credential(), key)
                else:
                    signer = Signer.from_priv_key_uri(uri, key)
                md.sign(signer, True)
            else:
                # offline signer, add empty sig
                md.signatures[key.keyid] = Signature(key.keyid, "")

        if rolename in ["timestamp", "snapshot"]:
            # repository should never write unsigned online roles
            self.root().verify_delegate(rolename, md.signed_bytes, md.signatures)

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

    def _validate_role(self, rolename: str) -> tuple[bool, str | None]:
        """Validate role compatibility with this repository

        Returns bool for validity and optional error message"""
        signed: Signed = self.open(rolename).signed
        known_good = self._known_good(rolename)

        # TODO: Current checks are more examples than actual checks

        # Make sure version grows if there are actual payload changes
        if known_good and known_good != signed:
            if signed.version <= known_good.version:
                return False, f"Version {signed.version} is not valid for {rolename}"

        days = signed.unrecognized_fields["x-tuf-on-ci-expiry-period"]
        if signed.expires > datetime.utcnow() + timedelta(days=days):
            return False, f"Expiry date is further than expected {days} days ahead"

        # TODO for root:
        # * check version is prev_version + 1
        # * check delegations are correct, consistent_snapshot is on

        # TODO for top-level targets:
        # * check delegations are expected
        # * check that target files in metadata match the files in targets/

        # TODO for delegated targets:
        # * check there are no delegations
        # * check that target files in metadata match the files in targets/
        # * check that target files in metadata are in the delegated path

        return True, None

    @staticmethod
    def _build_targets(target_dir: str, rolename: str) -> dict[str, TargetFile]:
        """Build a roles dict of TargetFile based on target files in a directory"""
        targetfiles = {}

        if rolename == "targets":
            root_dir = target_dir
        else:
            root_dir = os.path.join(target_dir, rolename)

        for fname in glob("*", root_dir=root_dir):
            realpath = os.path.join(root_dir, fname)
            if not os.path.isfile(realpath):
                continue

            # targetpath is a URL path, not OS path
            if rolename == "targets":
                targetpath = fname
            else:
                targetpath = f"{rolename}/{fname}"
            targetfiles[targetpath] = TargetFile.from_file(
                targetpath, realpath, ["sha256"]
            )

        return targetfiles

    def _known_good(self, rolename: str) -> Root | Targets | None:
        """Return object from the known-good repository state"""
        assert rolename not in [Timestamp.type, Snapshot.type]
        assert self._prev_dir is not None

        prev_path = os.path.join(self._prev_dir, f"{rolename}.json")
        if not os.path.exists(prev_path):
            return None

        with open(prev_path, "rb") as f:
            return Metadata.from_bytes(f.read()).signed

    def _get_target_changes(self, rolename: str) -> list[TargetState]:
        """Compare targetfiles in known good version and signing event version:
        return list of changes"""

        if rolename in ["root", "timestamp", "snapshot"]:
            return []

        changes = []

        targets = self._known_good(rolename)
        if targets is None:
            known_good_targetfiles = {}
        else:
            assert isinstance(targets, Targets)
            known_good_targetfiles = targets.targets

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

    def _get_verification_result(
        self, rolename: str, md: Metadata
    ) -> VerificationResultWithKeys:
        """Return verification result for rolename.

        Take into account that root must be verified by itself and the previous root.
        """
        if rolename == Root.type:
            # md may be modified if we're in close() persisting a new root:
            # we use that root as delegator instead of self.root()
            delegator: Root | Targets = md.signed
        elif rolename in [Timestamp.type, Snapshot.type, Targets.type]:
            delegator = self.root()
        else:
            delegator = self.targets()

        result = _get_verification_result(delegator, rolename, md)

        # If role is root and a previous version exists, verify with that too
        if rolename == Root.type:
            prev_delegator = self._known_good(Root.type)
            if prev_delegator:
                prev_result = _get_verification_result(prev_delegator, rolename, md)
                result = result.union(prev_result)

        return result

    def _get_invites(self, rolename: str) -> set[str]:
        """Return invites for roles delegations."""
        invites = set()

        # Build list of invites to all delegated roles of rolename
        delegation_names = []
        if rolename == Root.type:
            delegation_names = [Root.type, Targets.type]
        elif rolename == Targets.type:
            targets = self.targets()
            if targets.delegations and targets.delegations.roles:
                delegation_names = list(targets.delegations.roles.keys())

        for delegation_name in delegation_names:
            invites.update(self.state.invited_signers_for_role(delegation_name))

        return invites

    def status(self, rolename: str) -> SigningStatus:
        """Build signing status for role.

        This method relies on event state (.signing-event-state) to be accurate.
        Returns None only when known_good is True, and then in two cases: if delegating
        role is not root (because then the known good state is irrelevant) and also if
        there is no known good version yet.
        """
        invites = set()

        # Build list of invites to all delegated roles of rolename
        invites = self._get_invites(rolename)

        # Find out verification status (inluding which keys have signed)
        md = self.open(rolename)
        verification_result = self._get_verification_result(rolename, md)

        # Document changes to targets metadata in this signing event
        target_changes = self._get_target_changes(rolename)

        if invites or not verification_result.verified:
            valid, msg = False, None
        else:
            # Repository validation (metadata may be valid but still not acceptable)
            valid, msg = self._validate_role(rolename)

        return SigningStatus(invites, verification_result, target_changes, valid, msg)

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

        new_target_dict = self._build_targets(
            os.path.join(self._dir, "..", "targets"), rolename
        )
        with self.edit_targets(rolename) as targets:
            # if targets dict has no changes, cancel the metadata edit
            if targets.targets == new_target_dict:
                raise AbortEdit("No target changes needed")

            targets.targets = new_target_dict
            return True

        return False

    def is_signed(self, rolename: str) -> bool:
        """Return True if role is correctly signed and not in signing period

        NOTE: a role in signing period is valid for TUF clients but this method returns
        false in this case: this is useful when repository decides if it needs a new
        online role version.
        """
        md = self.open(rolename)
        if rolename in ["root", "timestamp", "snapshot", "targets"]:
            delegator: Root | Targets = self.root()
        else:
            delegator = self.targets()

        try:
            delegator.verify_delegate(rolename, md.signed_bytes, md.signatures)
        except UnsignedMetadataError:
            return False

        signing_days, _ = self.signing_expiry_period(rolename)
        delta = timedelta(days=signing_days)

        return datetime.utcnow() + delta < md.signed.expires
