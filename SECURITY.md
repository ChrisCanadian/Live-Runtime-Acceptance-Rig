# Security policy

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability that could expose
credentials, private evidence, or a live system. Use the private security
reporting feature of the repository host or contact the maintainer through an
already published private channel.

Include:

- affected version;
- minimal reproduction;
- potential impact;
- whether evidence contains sensitive data;
- suggested mitigation, if known.

Do not attach production databases, credentials, authorization headers, or
private traces.

## Evidence handling

Evidence bundles may contain durable records, identifiers, application
metadata, and binary backups. Treat them as sensitive until manually reviewed.
Public-safe redaction is defense in depth, not a publication guarantee.

Every programmatic run ID and evidence destination is resolved and required to
remain beneath the configured evidence root. Public-safe structured evidence
accepts only JSON-compatible values; unknown objects are rejected rather than
converted to strings after redaction.

Trace timestamp, sequence, run ID, event, suite, and case fields are
runtime-owned. Data collisions are rejected. Protected-text metadata uses a
per-run secret HMAC key so low-entropy values do not produce stable public
digests; the key is not written to evidence.

## Backup trust boundary

Database adapters return a structured BackupProof. File-backed evidence is not
accepted unless the exact expected destination:

- exists and is a regular file;
- has a positive size equal to the reported size;
- has an actual SHA-256 equal to a valid hexadecimal reported digest; and
- passes an integrity check invoked against that destination.

Non-file evidence must declare the remote evidence type and supply an explicit
BackupVerifier whose structured result targets the same snapshot. Reported
metadata alone is not proof. Backup restoration remains a separate operational
responsibility.

Adapters and application runtimes must not initialize or migrate durable state
during rig construction. Perform setup explicitly before the campaign so the
pre-write backup captures the actual starting state.

## Cleanup durability

Cases should call context.register_cleanup() immediately after every successful
durable mutation, or register_cleanups() for one atomic batch. Registration
validates the current run marker and non-empty identifier, suppresses
duplicates, updates the in-memory journal, and persists cleanup evidence.

CaseResult.cleanup_entries remains supported for compatibility, but a case that
raises cannot return it. Do not defer the only cleanup record until case return.

No cleanup runs automatically. Cleanup tooling must require both the exact
identifier and current run marker.

## Configuration

Ambient RIG_* values are ignored by default. Enable them only with the
--allow-env-overrides CLI flag or RIG_ALLOW_ENV_OVERRIDES=true in the
configuration file. environment.json records the source of important resolved
values, ignored ambient keys, and whether overrides were enabled.

## Campaign interpretation

An empty campaign, a selected suite with no non-skipped checks, or a campaign in
which every acceptance check is skipped is INCONCLUSIVE and exits nonzero with
NO_EXECUTED_ACCEPTANCE_CHECKS. Cleanup-manifest-only mode is the sole exemption.

Line coverage is not proof of these properties. Regression tests separately
exercise cleanup durability, backup verification, trace consistency, evidence
containment, configuration provenance, adapter lifecycle, and non-empty
acceptance execution.

## Supported versions

Until version 1.0, security fixes are applied to the latest released minor
version only.