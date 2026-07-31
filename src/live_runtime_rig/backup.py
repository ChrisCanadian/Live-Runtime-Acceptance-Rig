"""Independent validation for structured database backup proofs."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from .contracts import BackupProof, BackupVerification

_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


class BackupProofError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_reported_fields(proof: BackupProof) -> None:
    if proof.verified is not True or proof.integrity != "ok":
        raise BackupProofError("BACKUP_NOT_REPORTED_VERIFIED")
    if not isinstance(proof.size_bytes, int) or proof.size_bytes <= 0:
        raise BackupProofError("BACKUP_SIZE_INVALID")
    if not isinstance(proof.sha256, str) or not _SHA256.fullmatch(proof.sha256):
        raise BackupProofError("BACKUP_DIGEST_INVALID")


def verify_backup_proof(
    proof: Any,
    *,
    expected_destination: Path,
    database: Any,
) -> BackupVerification:
    """Verify a file locally or require an explicit verifier for remote evidence."""

    if not isinstance(proof, BackupProof):
        raise BackupProofError("BACKUP_PROOF_REQUIRED")
    _require_reported_fields(proof)

    if proof.evidence_type == "file":
        expected = expected_destination.resolve()
        target = Path(proof.target).resolve()
        if target != expected:
            raise BackupProofError("BACKUP_TARGET_MISMATCH")
        if not expected.is_file():
            raise BackupProofError("BACKUP_FILE_MISSING")
        actual_size = expected.stat().st_size
        if actual_size <= 0 or actual_size != proof.size_bytes:
            raise BackupProofError("BACKUP_SIZE_MISMATCH")
        actual_sha256 = _sha256(expected)
        if actual_sha256 != proof.sha256.lower():
            raise BackupProofError("BACKUP_DIGEST_MISMATCH")
        integrity = database.integrity_check(expected)
        if integrity.get("result") != "ok":
            raise BackupProofError("BACKUP_INTEGRITY_FAILED")
        return BackupVerification(
            target=str(expected),
            verified=True,
            integrity="ok",
            size_bytes=actual_size,
            sha256=actual_sha256,
        )

    if proof.evidence_type == "remote":
        if proof.verifier is None:
            raise BackupProofError("REMOTE_BACKUP_VERIFIER_REQUIRED")
        verification = proof.verifier.verify(proof)
        if not isinstance(verification, BackupVerification):
            raise BackupProofError("REMOTE_BACKUP_VERIFICATION_INVALID")
        if verification.target != proof.target:
            raise BackupProofError("BACKUP_TARGET_MISMATCH")
        if (
            verification.verified is not True
            or verification.integrity != "ok"
            or verification.size_bytes != proof.size_bytes
            or verification.sha256.lower() != proof.sha256.lower()
        ):
            raise BackupProofError("REMOTE_BACKUP_VERIFICATION_FAILED")
        return verification

    raise BackupProofError("BACKUP_EVIDENCE_TYPE_UNSUPPORTED")
