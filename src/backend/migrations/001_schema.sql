-- DrugTree Database Schema
-- Initial migration creating the drugs table

CREATE TABLE IF NOT EXISTS drugs (
    id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(500) NOT NULL,
    smiles TEXT,
    inchikey VARCHAR(50),
    atc_code VARCHAR(10),
    atc_category CHAR(1),
    molecular_weight REAL,
    phase VARCHAR(20),
    year_approved INTEGER,
    generation INTEGER,
    indication TEXT,
    targets TEXT[],
    company VARCHAR(255),
    synonyms TEXT[],
    class VARCHAR(255),
    parent_drugs TEXT[],
    clinical_trials TEXT[],
    kegg_id VARCHAR(50),
    body_region VARCHAR(100),
    secondary_body_regions TEXT[],
    chembl_id VARCHAR(50),
    pubchem_cid INTEGER,
    is_curated BOOLEAN DEFAULT false,
    provenance JSONB DEFAULT '{}',
    source VARCHAR(50) DEFAULT 'json',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index onCREATE INDEX IF NOT EXISTS idx_drugs_name ON drugs(name);
CREATE INDEX IF NOT EXISTS idx_drugs_atc_code on drugs(atc_code);
CREATE INDEX IF NOT EXISTS idx_drugs_atc_category on drugs(atc_category);
CREATE INDEX IF NOT EXISTS idx_drugs_chembl_id on drugs(chembl_id);
CREATE INDEX IF NOT EXISTS idx_drugs_kegg_id on drugs(kegg_id);

-- Comments
COMMENT 'Drugs table with ATC classification andcomment onTable drugs stores all approved small-molecule drugs withcomment 'atc_code follows WHO Anatomical Therapeutic Chemical classification
comment 'atc_category is the first-level ATC category (A-V)
comment 'provenance tracks data sources andcomment 'source indicates where the data came from: json, chembl
 pubchem
 internal
