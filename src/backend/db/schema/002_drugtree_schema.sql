-- DrugTree PostgreSQL Schema
-- Version: 2.0.0
-- Created: 2026-03-15
-- Purpose: Main schema for drugs, ATC codes, and provenance tracking

-- ============================================
-- DRUGS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS drugs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    smiles TEXT,
    inchikey TEXT,
    
    -- ATC Classification (primary)
    atc_code TEXT,
    atc_category CHAR(1),
    
    -- Drug Properties
    molecular_weight REAL,
    phase TEXT,
    year_approved INTEGER,
    generation INTEGER DEFAULT 1,
    indication TEXT,
    targets TEXT[] DEFAULT '{}',
    company TEXT,
    synonyms TEXT[] DEFAULT '{}',
    class TEXT,
    
    -- External IDs
    kegg_id TEXT,
    chembl_id TEXT,
    pubchem_cid INTEGER,
    
    -- Body Region Mapping
    body_region TEXT,
    secondary_body_regions TEXT[] DEFAULT '{}',
    
    -- Clinical Data
    clinical_trials TEXT[] DEFAULT '{}',
    
    -- Curation Flag
    is_curated BOOLEAN DEFAULT FALSE,
    
    -- Provenance (JSONB for flexibility)
    provenance JSONB DEFAULT '{}',
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- ATC CODES TABLE (Normalized)
-- ============================================
CREATE TABLE IF NOT EXISTS atc_codes (
    code TEXT PRIMARY KEY,  -- Full ATC code (e.g., C10AA05)
    category CHAR(1) NOT NULL,  -- Level 1 category (e.g., C)
    level2 TEXT,  -- Level 2 (e.g., 10)
    level3 TEXT,  -- Level 3 (e.g., AA)
    level4 TEXT,  -- Level 4 (e.g., 05)
    
    -- Classification Names
    level1_name TEXT,  -- e.g., "Cardiovascular System"
    level2_name TEXT,  -- e.g., "Lipid Modifying Agents"
    level3_name TEXT,  -- e.g., "HMG CoA reductase inhibitors"
    level4_name TEXT,  -- e.g., "atorvastatin"
    
    -- Metadata
    is_placeholder BOOLEAN DEFAULT FALSE,  -- True for XX99 codes
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- DRUG-ATC MAPPING (Many-to-Many)
-- ============================================
CREATE TABLE IF NOT EXISTS drug_atc_mapping (
    id SERIAL PRIMARY KEY,
    drug_id TEXT NOT NULL REFERENCES drugs(id) ON DELETE CASCADE,
    atc_code TEXT NOT NULL REFERENCES atc_codes(code) ON DELETE CASCADE,
    
    -- Classification Metadata
    is_primary BOOLEAN DEFAULT TRUE,  -- Primary ATC code for this drug
    source TEXT NOT NULL,  -- e.g., 'chembl', 'kegg', 'pubchem', 'heuristic'
    confidence REAL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
    
    -- Timestamps
    retrieved_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Unique Constraint
    UNIQUE(drug_id, atc_code)
);

-- ============================================
-- UPDATE LOG (Audit Trail)
-- ============================================
CREATE TABLE IF NOT EXISTS update_log (
    id SERIAL PRIMARY KEY,
    source TEXT NOT NULL,  -- e.g., 'chembl', 'kegg', 'pubchem', 'fda'
    action TEXT NOT NULL,  -- e.g., 'sync', 'enrich', 'validate'
    
    -- Statistics
    records_processed INTEGER DEFAULT 0,
    records_added INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    records_failed INTEGER DEFAULT 0,
    
    -- Status
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    error_message TEXT,
    
    -- Timestamps
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE
);

-- ============================================
-- INDEXES
-- ============================================

-- Drugs Table Indexes
CREATE INDEX IF NOT EXISTS idx_drugs_atc_code ON drugs(atc_code);
CREATE INDEX IF NOT EXISTS idx_drugs_atc_category ON drugs(atc_category);
CREATE INDEX IF NOT EXISTS idx_drugs_kegg_id ON drugs(kegg_id);
CREATE INDEX IF NOT EXISTS idx_drugs_chembl_id ON drugs(chembl_id);
CREATE INDEX IF NOT EXISTS idx_drugs_pubchem_cid ON drugs(pubchem_cid);
CREATE INDEX IF NOT EXISTS idx_drugs_inchikey ON drugs(inchikey);
CREATE INDEX IF NOT EXISTS idx_drugs_body_region ON drugs(body_region);
CREATE INDEX IF NOT EXISTS idx_drugs_is_curated ON drugs(is_curated);
CREATE INDEX IF NOT EXISTS idx_drugs_name ON drugs USING gin(to_tsvector('english', name));

-- ATC Codes Indexes
CREATE INDEX IF NOT EXISTS idx_atc_codes_category ON atc_codes(category);
CREATE INDEX IF NOT EXISTS idx_atc_codes_is_placeholder ON atc_codes(is_placeholder);

-- Drug-ATC Mapping Indexes
CREATE INDEX IF NOT EXISTS idx_mapping_drug_id ON drug_atc_mapping(drug_id);
CREATE INDEX IF NOT EXISTS idx_mapping_atc_code ON drug_atc_mapping(atc_code);
CREATE INDEX IF NOT EXISTS idx_mapping_source ON drug_atc_mapping(source);
CREATE INDEX IF NOT EXISTS idx_mapping_primary ON drug_atc_mapping(drug_id, is_primary) WHERE is_primary = TRUE;

-- Update Log Indexes
CREATE INDEX IF NOT EXISTS idx_update_log_source ON update_log(source);
CREATE INDEX IF NOT EXISTS idx_update_log_status ON update_log(status);
CREATE INDEX IF NOT EXISTS idx_update_log_started ON update_log(started_at);

-- ============================================
-- TRIGGERS
-- ============================================

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_drugs_updated_at BEFORE UPDATE ON drugs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- COMMENTS
-- ============================================

COMMENT ON TABLE drugs IS 'Main drug records - one row per unique drug compound';
COMMENT ON TABLE atc_codes IS 'Normalized ATC classification codes with hierarchical names';
COMMENT ON TABLE drug_atc_mapping IS 'Many-to-many relationship between drugs and ATC codes with provenance';
COMMENT ON TABLE update_log IS 'Audit trail for all data synchronization operations';

-- ============================================
-- DOWN MIGRATION (Rollback)
-- ============================================
-- To rollback, run these commands in reverse order:
-- DROP TABLE IF EXISTS update_log CASCADE;
-- DROP TABLE IF EXISTS drug_atc_mapping CASCADE;
-- DROP TABLE IF EXISTS atc_codes CASCADE;
-- DROP TABLE IF EXISTS drugs CASCADE;
-- DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE;
