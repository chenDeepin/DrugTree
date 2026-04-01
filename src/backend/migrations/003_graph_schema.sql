-- DrugTree Graph Schema Migration
-- Purpose: upgrade the SQLite schema from a mostly drug-centered model to a
-- multi-entity typed graph model by adding graph edge tables, evidence source
-- metadata, cross-reference tables, and non-destructive column extensions.
-- Notes: JSON arrays are stored as TEXT, timestamps are stored as TEXT using
-- CURRENT_TIMESTAMP, and existing tables/data are preserved in place.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS evidence_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    base_url TEXT,
    version TEXT,
    license TEXT,
    last_retrieved TEXT,
    description TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS drug_target_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    drug_id TEXT NOT NULL REFERENCES drugs(id) ON DELETE CASCADE,
    target_id TEXT NOT NULL REFERENCES targets(id) ON DELETE CASCADE,
    interaction_type TEXT DEFAULT 'unknown',
    mechanism_of_action TEXT,
    evidence_sources TEXT DEFAULT '[]',
    confidence REAL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
    clinical_phase TEXT,
    retrieved_at TEXT DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(drug_id, target_id, interaction_type)
);

CREATE TABLE IF NOT EXISTS target_disease_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id TEXT NOT NULL REFERENCES targets(id) ON DELETE CASCADE,
    disease_id TEXT NOT NULL REFERENCES diseases(id) ON DELETE CASCADE,
    association_score REAL,
    evidence_type TEXT,
    evidence_sources TEXT DEFAULT '[]',
    confidence REAL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
    retrieved_at TEXT DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(target_id, disease_id, evidence_type)
);

CREATE TABLE IF NOT EXISTS drug_bodyregion_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    drug_id TEXT NOT NULL REFERENCES drugs(id) ON DELETE CASCADE,
    body_region TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    system_flag INTEGER DEFAULT 0,
    placement_basis TEXT,
    evidence_sources TEXT DEFAULT '[]',
    confidence REAL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(drug_id, body_region, relationship_type)
);

CREATE TABLE IF NOT EXISTS drug_xrefs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    drug_id TEXT NOT NULL REFERENCES drugs(id) ON DELETE CASCADE,
    source_name TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_url TEXT,
    is_primary INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(drug_id, source_name, source_id)
);

CREATE TABLE IF NOT EXISTS target_xrefs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id TEXT NOT NULL REFERENCES targets(id) ON DELETE CASCADE,
    source_name TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_url TEXT,
    is_primary INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(target_id, source_name, source_id)
);

-- These columns are absent in the pre-003 schema. The migration runner records
-- applied filenames and executes each migration file once per database.
ALTER TABLE targets ADD COLUMN ensembl_gene_id TEXT;
ALTER TABLE targets ADD COLUMN gene_type TEXT DEFAULT 'protein_coding';
ALTER TABLE targets ADD COLUMN pathway_ids TEXT DEFAULT '[]';
ALTER TABLE targets ADD COLUMN druggability TEXT DEFAULT 'unknown';
ALTER TABLE targets ADD COLUMN is_validated_target INTEGER DEFAULT 0;

ALTER TABLE diseases ADD COLUMN disease_hierarchy TEXT DEFAULT '[]';
ALTER TABLE diseases ADD COLUMN is_body_region_mapped INTEGER DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_evidence_sources_source_name ON evidence_sources(source_name);
CREATE INDEX IF NOT EXISTS idx_evidence_sources_source_type ON evidence_sources(source_type);

CREATE INDEX IF NOT EXISTS idx_drug_target_edges_drug_id ON drug_target_edges(drug_id);
CREATE INDEX IF NOT EXISTS idx_drug_target_edges_target_id ON drug_target_edges(target_id);
CREATE INDEX IF NOT EXISTS idx_drug_target_edges_confidence ON drug_target_edges(confidence);

CREATE INDEX IF NOT EXISTS idx_target_disease_edges_target_id ON target_disease_edges(target_id);
CREATE INDEX IF NOT EXISTS idx_target_disease_edges_disease_id ON target_disease_edges(disease_id);
CREATE INDEX IF NOT EXISTS idx_target_disease_edges_confidence ON target_disease_edges(confidence);

CREATE INDEX IF NOT EXISTS idx_drug_bodyregion_edges_drug_id ON drug_bodyregion_edges(drug_id);
CREATE INDEX IF NOT EXISTS idx_drug_bodyregion_edges_body_region ON drug_bodyregion_edges(body_region);
CREATE INDEX IF NOT EXISTS idx_drug_bodyregion_edges_confidence ON drug_bodyregion_edges(confidence);

CREATE INDEX IF NOT EXISTS idx_drug_xrefs_drug_id ON drug_xrefs(drug_id);
CREATE INDEX IF NOT EXISTS idx_drug_xrefs_source_name ON drug_xrefs(source_name);

CREATE INDEX IF NOT EXISTS idx_target_xrefs_target_id ON target_xrefs(target_id);
CREATE INDEX IF NOT EXISTS idx_target_xrefs_source_name ON target_xrefs(source_name);
