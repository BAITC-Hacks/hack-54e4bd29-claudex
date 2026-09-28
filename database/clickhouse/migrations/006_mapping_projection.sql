-- Immutable candidate rows; activated exclusively by verified PostgreSQL pointer.
-- kind distinguishes organization/region. Organizations expose canonical_id as hospital_id at read time.
CREATE TABLE IF NOT EXISTS mapping_projection
(
    version String,
    kind LowCardinality(String),
    identity_space LowCardinality(String),
    source_key String,
    canonical_id UUID
)
ENGINE = MergeTree
ORDER BY (version, kind, identity_space, source_key);
