from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from live_runtime_rig.backup import BackupProofError, verify_backup_proof
from live_runtime_rig.contracts import BackupProof, BackupVerification


class IntegrityDatabase:
    def __init__(self) -> None:
        self.targets = []

    def integrity_check(self, path=None):
        self.targets.append(path)
        return {"result": "ok"}


def _file_proof(path) -> BackupProof:
    content = path.read_bytes()
    return BackupProof(
        evidence_type="file",
        target=str(path.resolve()),
        verified=True,
        integrity="ok",
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        method="test-copy",
    )


def test_file_backup_proof_matches_actual_destination_bytes(tmp_path) -> None:
    destination = tmp_path / "backup.sqlite"
    destination.write_bytes(b"real backup")
    database = IntegrityDatabase()

    verification = verify_backup_proof(
        _file_proof(destination),
        expected_destination=destination,
        database=database,
    )

    assert verification.target == str(destination.resolve())
    assert verification.verified is True
    assert database.targets == [destination.resolve()]


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"size_bytes": 999}, "BACKUP_SIZE_MISMATCH"),
        ({"sha256": "z" * 64}, "BACKUP_DIGEST_INVALID"),
        ({"sha256": "0" * 64}, "BACKUP_DIGEST_MISMATCH"),
        ({"target": "another.sqlite"}, "BACKUP_TARGET_MISMATCH"),
    ],
)
def test_file_backup_rejects_false_reported_properties(tmp_path, change, code) -> None:
    destination = tmp_path / "backup.sqlite"
    destination.write_bytes(b"real backup")
    proof = replace(_file_proof(destination), **change)

    with pytest.raises(BackupProofError, match=code):
        verify_backup_proof(
            proof,
            expected_destination=destination,
            database=IntegrityDatabase(),
        )


def test_file_backup_requires_regular_existing_file(tmp_path) -> None:
    destination = tmp_path / "missing.sqlite"
    proof = BackupProof(
        evidence_type="file",
        target=str(destination),
        verified=True,
        integrity="ok",
        size_bytes=1,
        sha256="0" * 64,
        method="lying-adapter",
    )
    with pytest.raises(BackupProofError, match="BACKUP_FILE_MISSING"):
        verify_backup_proof(
            proof,
            expected_destination=destination,
            database=IntegrityDatabase(),
        )


def test_remote_backup_requires_explicit_verifier(tmp_path) -> None:
    proof = BackupProof(
        evidence_type="remote",
        target="snapshot://example/one",
        verified=True,
        integrity="ok",
        size_bytes=4,
        sha256=hashlib.sha256(b"data").hexdigest(),
        method="remote-snapshot",
    )
    with pytest.raises(BackupProofError, match="REMOTE_BACKUP_VERIFIER_REQUIRED"):
        verify_backup_proof(
            proof,
            expected_destination=tmp_path / "unused",
            database=IntegrityDatabase(),
        )


def test_remote_backup_uses_explicit_verifier_contract(tmp_path) -> None:
    digest = hashlib.sha256(b"data").hexdigest()

    class Verifier:
        def verify(self, proof):
            return BackupVerification(
                target=proof.target,
                verified=True,
                integrity="ok",
                size_bytes=4,
                sha256=digest,
            )

    proof = BackupProof(
        evidence_type="remote",
        target="snapshot://example/one",
        verified=True,
        integrity="ok",
        size_bytes=4,
        sha256=digest,
        method="remote-snapshot",
        verifier=Verifier(),
    )
    assert verify_backup_proof(
        proof,
        expected_destination=tmp_path / "unused",
        database=IntegrityDatabase(),
    ).verified
