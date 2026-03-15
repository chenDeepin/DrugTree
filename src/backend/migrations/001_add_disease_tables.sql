-- DrugTree Disease Universe Schema
-- Creates tables for disease, target, and drug-disease relationships
-- Version: 1.0.0
-- Created: 2026-03-14

-- Enable foreign keys (SQLite)
PRAGMA foreign_keys = ON;

-- Diseases table
CREATE TABLE IF NOT EXISTS diseases (
    id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    synonyms TEXT DEFAULT '[]',  -- JSON array
    body_region TEXT NOT NULL,
    anatomy_nodes TEXT DEFAULT '[]',  -- JSON array
    orphan_flag INTEGER DEFAULT 0,
    prevalence_tier TEXT DEFAULT 'unknown',
    prevalence_count INTEGER,
    evidence_level TEXT DEFAULT 'unknown',
    mechanism_summary TEXT,
    mechanism_citation TEXT,
    target_count INTEGER DEFAULT 0,
    approved_drug_count INTEGER DEFAULT 0,
    clinical_drug_count INTEGER DEFAULT 0,
    mondo_id TEXT,
    doid_id TEXT,
    icd10_code TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Targets table
CREATE TABLE IF NOT EXISTS targets (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    name TEXT NOT NULL,
    modality TEXT DEFAULT 'unknown',
    disease_ids TEXT DEFAULT '[]',  -- JSON array
    uniprot_id TEXT,
    hgnc_id TEXT,
    entrez_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Drug-Disease edges (many-to-many relationship)
CREATE TABLE IF NOT EXISTS drug_disease_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    drug_id TEXT NOT NULL,
    disease_id TEXT NOT NULL,
    indication_type TEXT DEFAULT 'primary',
    evidence_source TEXT NOT NULL,
    evidence_level TEXT DEFAULT 'unknown',
    confidence REAL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
    phase_context TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(drug_id, disease_id, evidence_source)
);

-- Regional approvals (v1: FDA only)
CREATE TABLE IF NOT EXISTS regional_approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    drug_id TEXT NOT NULL,
    region TEXT NOT NULL CHECK (region IN ('FDA')),
    status TEXT NOT NULL CHECK (status IN ('approved', 'approved_with_warnings', 'under_review', 'withdrawn', 'not_submitted')),
    approval_date TEXT,  -- ISO 8601 format
    label_source TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(drug_id, region)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_diseases_body_region ON diseases(body_region);
CREATE INDEX IF NOT EXISTS idx_diseases_orphan ON diseases(orphan_flag);
CREATE INDEX IF NOT EXISTS idx_diseases_prevalence ON diseases(prevalence_tier);
CREATE INDEX IF NOT EXISTS idx_targets_symbol ON targets(symbol);
CREATE INDEX IF NOT EXISTS idx_targets_uniprot ON targets(uniprot_id);
CREATE INDEX IF NOT EXISTS idx_edges_drug ON drug_disease_edges(drug_id);
CREATE INDEX IF NOT EXISTS idx_edges_disease ON drug_disease_edges(disease_id);
CREATE INDEX IF NOT EXISTS idx_edges_evidence ON drug_disease_edges(evidence_level);
CREATE INDEX IF NOT EXISTS idx_approvals_drug ON regional_approvals(drug_id);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON regional_approvals(status);

-- Full-text search for disease names and synonyms (optional, SQLite FTS5)
CREATE VIRTUAL TABLE IF NOT EXISTS diseases_fts USING fts5(
    id UNINDEXED,
    canonical_name,
    synonyms,
    content='diseases',
    content_rowid='rowid'
);

-- Triggers to keep FTS index in sync
CREATE TRIGGER IF NOT EXISTS diseases_ai AFTER INSERT ON diseases BEGIN
    INSERT INTO diseases_fts(rowid, id, canonical_name, synonyms)
    VALUES (new.rowid, new.id, new.canonical_name, new.synonyms);
END;

CREATE TRIGGER IF NOT EXISTS diseases_ad AFTER DELETE ON diseases BEGIN
    INSERT INTO diseases_fts(diseases_fts, rowid, id, canonical_name, synonyms)
    VALUES ('delete', old.rowid, old.id, old.canonical_name, old.synonyms);
END;

CREATE TRIGGER IF NOT EXISTS diseases_au AFTER UPDATE ON diseases BEGIN
    INSERT INTO diseases_fts(diseases_fts, rowid, id, canonical_name, synonyms)
    VALUES ('delete', old.rowid, old.id, old.canonical_name, old.synonyms);
    INSERT INTO diseases_fts(rowid, id, canonical_name, synonyms)
    VALUES (new.rowid, new.id, new.canonical_name, new.synonyms);
END;
