# Changelog

All notable changes will be documented in this file.

The format follows Keep a Changelog, and the project intends to use Semantic
Versioning.

## [Unreleased]

## [0.1.1] - 2026-07-31

### Security

- Validate structured file-backed backup proofs against the exact destination,
  regular-file status, size, hexadecimal SHA-256, and targeted integrity result.
- Require an explicit verifier contract for non-file backup evidence.
- Contain run IDs and every evidence write beneath the configured evidence root.
- Reserve runtime-owned trace metadata and reject collision attempts.
- Reject non-JSON evidence objects instead of stringifying them after redaction.
- Replace stable protected-text digests with per-run keyed HMAC-SHA256 metadata.

### Fixed

- Persist cleanup entries incrementally so later case exceptions cannot erase
  evidence of earlier durable writes.
- Make cleanup batch validation atomic, reject empty identifiers, and suppress
  duplicate entries.
- Record case span failures with success=false and the actual exception type.
- Return INCONCLUSIVE with NO_EXECUTED_ACCEPTANCE_CHECKS for empty or all-skipped
  campaigns; cleanup-manifest-only mode remains exempt.
- Mark adapter close failures as framework errors and close database adapters.
- Contain finalization failures and return a framework error instead of raising.
- Reject duplicate sanitized case evidence names before executing cases.
- Remove example database mutation from adapter and runtime initialization.

### Changed

- Ambient RIG_* overrides require explicit opt-in and resolved provenance is
  recorded in environment.json.
- Network-required metadata now comes from configuration.
- Database adapters return BackupProof and expose close().
- Cases may call context.register_cleanup() or context.register_cleanups()
  immediately after successful mutations.
- The toy example database must be seeded explicitly before running a campaign.

### Tests

- Add regression probes for all confirmed failure modes and the reproduced
  lifecycle, collision, redaction, and finalization risks.

## [0.1.0] - 2026-07-30

### Added

- Runnable command-line acceptance framework.
- Explicit PASS, FAIL, and SKIP assertion ledger.
- Runtime, database, and case adapter contracts.
- Verified SQLite backup and strict table-allowlist helpers.
- Public-safe redaction and protected-text metadata.
- Structured evidence and cleanup manifests.
- In-process FastAPI and SQLite work-order example.
- Passing and intentional failing campaign configurations.
- Automated framework and example tests.
