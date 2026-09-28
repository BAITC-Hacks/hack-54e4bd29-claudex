# ADR-0019: Versioned mapping projection and effective scope

Date: 2026-09-23. Implementation decision for the approved pilot consolidation plan.

PostgreSQL owns decisions and a serialized generation pointer. Every approval or revocation advances the generation and immediately invalidates the prior projection for dependent queries. Immutable candidates contain exact identity_space + source_key mappings, canonical IDs, digest and decision evidence; ambiguous legacy identities are excluded.

ClickHouse stores immutable versioned rows. Publication verifies count and digest before moving the PG active pointer. A crash before pointer commit leaves the candidate inactive. Retrying verifies existing rows and never appends duplicates. A corrupt partial candidate is unavailable, requiring explicit repair; no broad delete is automatic.

Queries resolve exact approved mappings before scope and aggregation. Cache keys include the mapping version and delivery allowlist. Restricted queries reject unavailable mapping and recheck the pointer before returning. Consumers that atomically persist scope-dependent results take the same PG advisory transaction lock (64730102) through final persistence, then delivery source locks in that order.

Legacy imports remain historical; only published reviewed delivery IDs enter operational readers. No change to ADR-0008 or signal deduplication. No profile mapping until an official canonical dimension exists. Owner references and approvals remain EXTERNAL DEPENDENCY.
