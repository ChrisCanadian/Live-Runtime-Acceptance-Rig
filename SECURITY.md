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

Evidence bundles may contain durable records, digests, identifiers, application
metadata, and binary backups. Treat them as sensitive until manually reviewed.
Public-safe redaction is defense in depth, not a publication guarantee.

## Supported versions

Until version 1.0, security fixes are applied to the latest released minor
version only.
