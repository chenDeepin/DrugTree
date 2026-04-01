#!/usr/bin/env python3
"""Load canonical JSONL edges and xrefs into the SQLite graph tables.

Reads from data/processed/*.jsonl and data/processed/*_xrefs.json,
writes into the 003 graph schema tables (drug_target_edges, target_disease_edges,
drug_xrefs, target_xrefs, evidence_sources).

Requires existing drugs, targets, and diseases rows in the SQLite database.
Run migrations first, then seed those tables, then this script.

Usage:
    python3 -m src.backend.etl.load_graph_edges [--db-path drugtree.db]
"""

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
PROCESSED_DIR = DATA_DIR / "processed"
MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    records: List[Dict[str, Any]] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _load_json(path: Path) -> Any:
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def _existing_ids(conn: sqlite3.Connection, table: str) -> Set[str]:
    rows = conn.execute(f"SELECT id FROM {table}").fetchall()
    return {r[0] for r in rows}


POSTGRES_ONLY_MIGRATIONS = {"001_schema.sql"}


def _ensure_drugs_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS drugs (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            smiles TEXT,
            inchikey TEXT,
            atc_code TEXT,
            atc_category TEXT,
            molecular_weight REAL,
            phase TEXT,
            year_approved INTEGER,
            generation INTEGER,
            indication TEXT,
            targets TEXT DEFAULT '[]',
            company TEXT,
            synonyms TEXT DEFAULT '[]',
            class TEXT,
            parent_drugs TEXT DEFAULT '[]',
            clinical_trials TEXT DEFAULT '[]',
            kegg_id TEXT,
            body_region TEXT,
            secondary_body_regions TEXT DEFAULT '[]',
            chembl_id TEXT,
            pubchem_cid INTEGER,
            is_curated INTEGER DEFAULT 0,
            provenance TEXT DEFAULT '{}',
            source TEXT DEFAULT 'json',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)


def run_migration(conn: sqlite3.Connection) -> None:
    _ensure_drugs_table(conn)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    for mig_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if mig_file.name in POSTGRES_ONLY_MIGRATIONS:
            continue
        logger.info("Applying migration: %s", mig_file.name)
        with open(mig_file) as f:
            sql = f.read()
        try:
            conn.executescript(sql)
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                logger.debug("Column already exists, skipping: %s", e)
            elif (
                "duplicate table" in str(e).lower()
                or "already exists" in str(e).lower()
            ):
                logger.debug("Table already exists, skipping: %s", e)
            else:
                raise
        conn.commit()


def seed_drugs(conn: sqlite3.Connection) -> int:
    """Insert drug records from canonical drugs.json."""
    drugs_path = DATA_DIR / "drugs.json"
    payload = _load_json(drugs_path)
    drugs = payload.get("drugs", []) if isinstance(payload, dict) else payload

    existing = _existing_ids(conn, "drugs")
    inserted = 0
    for drug in drugs:
        drug_id = str(drug.get("id", ""))
        if not drug_id or drug_id in existing:
            continue
        try:
            conn.execute(
                """INSERT OR IGNORE INTO drugs (id, name, smiles, inchikey, atc_code,
                   atc_category, molecular_weight, phase, year_approved, generation,
                   indication, targets, company, synonyms, class, parent_drugs,
                   clinical_trials, kegg_id, body_region, secondary_body_regions,
                   chembl_id, pubchem_cid, is_curated, provenance, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                           ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    drug_id,
                    str(drug.get("name", "")),
                    drug.get("smiles"),
                    drug.get("inchikey"),
                    drug.get("atc_code"),
                    drug.get("atc_category"),
                    drug.get("molecular_weight"),
                    drug.get("phase"),
                    drug.get("year_approved"),
                    drug.get("generation"),
                    drug.get("indication"),
                    json.dumps(drug.get("targets", [])),
                    drug.get("company"),
                    json.dumps(drug.get("synonyms", [])),
                    drug.get("class"),
                    json.dumps(drug.get("parent_drugs", [])),
                    json.dumps(drug.get("clinical_trials", [])),
                    drug.get("kegg_id"),
                    drug.get("body_region"),
                    json.dumps(drug.get("secondary_body_regions", [])),
                    drug.get("chembl_id"),
                    drug.get("pubchem_cid"),
                    1 if drug.get("is_curated") else 0,
                    json.dumps(drug.get("provenance", {})),
                    drug.get("source", "json"),
                ),
            )
            inserted += 1
        except Exception as e:
            logger.warning("Failed to insert drug %s: %s", drug_id, e)
    conn.commit()
    logger.info(
        "Seeded %d drugs (total now: %d)", inserted, len(_existing_ids(conn, "drugs"))
    )
    return inserted


def seed_diseases(conn: sqlite3.Connection) -> int:
    """Insert disease records from canonical diseases.json."""
    diseases_path = DATA_DIR / "diseases.json"
    payload = _load_json(diseases_path)
    diseases = payload.get("diseases", []) if isinstance(payload, dict) else payload

    existing = _existing_ids(conn, "diseases")
    inserted = 0
    for disease in diseases:
        disease_id = str(disease.get("id", ""))
        if not disease_id or disease_id in existing:
            continue
        try:
            conn.execute(
                """INSERT OR IGNORE INTO diseases
                   (id, canonical_name, synonyms, body_region, anatomy_nodes,
                    orphan_flag, prevalence_tier, prevalence_count, evidence_level,
                    mechanism_summary, mechanism_citation, target_count,
                    approved_drug_count, clinical_drug_count, mondo_id, doid_id,
                    icd10_code, disease_hierarchy, is_body_region_mapped)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    disease_id,
                    str(disease.get("canonical_name") or disease.get("name", "")),
                    json.dumps(disease.get("synonyms", [])),
                    str(disease.get("body_region", "")),
                    json.dumps(disease.get("anatomy_nodes", [])),
                    1 if disease.get("orphan_flag") else 0,
                    str(disease.get("prevalence_tier", "unknown")),
                    disease.get("prevalence_count"),
                    str(disease.get("evidence_level", "unknown")),
                    disease.get("mechanism_summary"),
                    disease.get("mechanism_citation"),
                    disease.get("target_count", 0),
                    disease.get("approved_drug_count", 0),
                    disease.get("clinical_drug_count", 0),
                    disease.get("mondo_id"),
                    disease.get("doid_id"),
                    disease.get("icd10_code"),
                    json.dumps(disease.get("disease_hierarchy", [])),
                    1 if disease.get("is_body_region_mapped") else 0,
                ),
            )
            inserted += 1
        except Exception as e:
            logger.warning("Failed to insert disease %s: %s", disease_id, e)
    conn.commit()
    logger.info(
        "Seeded %d diseases (total now: %d)",
        inserted,
        len(_existing_ids(conn, "diseases")),
    )
    return inserted


def seed_targets(conn: sqlite3.Connection) -> int:
    """Insert target records from normalized nodes_target.jsonl."""
    target_path = PROCESSED_DIR / "nodes_target.jsonl"
    records = _load_jsonl(target_path)

    existing: Set[str] = _existing_ids(conn, "targets")
    inserted = 0
    for rec in records:
        node_id = str(rec.get("node_id", ""))
        # node_id is like "target:ADRB1" — extract symbol
        if node_id.startswith("target:"):
            symbol = node_id.split(":", 1)[1]
        else:
            symbol = node_id
        if not symbol or symbol in existing:
            continue
        extra = rec.get("extra", {})
        try:
            conn.execute(
                """INSERT OR IGNORE INTO targets
                   (id, symbol, name, modality, disease_ids, uniprot_id,
                    hgnc_id, entrez_id, ensembl_gene_id, gene_type, pathway_ids,
                    druggability, is_validated_target)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    symbol,
                    symbol,
                    extra.get("name") or symbol,
                    extra.get("modality", "unknown"),
                    json.dumps(extra.get("disease_ids", [])),
                    extra.get("uniprot_id"),
                    extra.get("hgnc_id"),
                    extra.get("entrez_id"),
                    extra.get("ensembl_gene_id"),
                    extra.get("gene_type", "protein_coding"),
                    json.dumps(extra.get("pathway_ids", [])),
                    extra.get("druggability", "unknown"),
                    1 if extra.get("is_validated_target") else 0,
                ),
            )
            inserted += 1
        except Exception as e:
            logger.warning("Failed to insert target %s: %s", symbol, e)
    conn.commit()
    logger.info(
        "Seeded %d targets (total now: %d)",
        inserted,
        len(_existing_ids(conn, "targets")),
    )
    return inserted


def load_drug_target_edges(conn: sqlite3.Connection) -> int:
    """Load drug-target edges from edges_drug_target.jsonl."""
    edge_path = PROCESSED_DIR / "edges_drug_target.jsonl"
    records = _load_jsonl(edge_path)
    if not records:
        logger.info("No drug-target edges to load")
        return 0

    valid_drugs = _existing_ids(conn, "drugs")
    valid_targets = _existing_ids(conn, "targets")
    inserted = 0
    for rec in records:
        extra = rec.get("extra", {})
        drug_id = str(extra.get("drug_id", ""))
        target_id = str(extra.get("target_id", ""))
        if drug_id not in valid_drugs or target_id not in valid_targets:
            continue
        try:
            conn.execute(
                """INSERT OR IGNORE INTO drug_target_edges
                   (drug_id, target_id, interaction_type, mechanism_of_action,
                    evidence_sources, confidence, clinical_phase, retrieved_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    drug_id,
                    target_id,
                    extra.get("interaction_type", "unknown"),
                    extra.get("mechanism_of_action"),
                    json.dumps(extra.get("evidence_sources", [])),
                    float(rec.get("confidence", 1.0)),
                    extra.get("clinical_phase"),
                    extra.get("retrieved_at"),
                ),
            )
            inserted += 1
        except Exception as e:
            logger.warning(
                "Failed to insert drug-target edge %s-%s: %s", drug_id, target_id, e
            )
    conn.commit()
    logger.info("Loaded %d drug-target edges", inserted)
    return inserted


def load_target_disease_edges(conn: sqlite3.Connection) -> int:
    """Load target-disease edges from edges_target_disease.jsonl."""
    edge_path = PROCESSED_DIR / "edges_target_disease.jsonl"
    records = _load_jsonl(edge_path)
    if not records:
        logger.info("No target-disease edges to load")
        return 0

    valid_targets = _existing_ids(conn, "targets")
    valid_diseases = _existing_ids(conn, "diseases")
    inserted = 0
    for rec in records:
        extra = rec.get("extra", {})
        target_id = str(extra.get("target_id", ""))
        disease_id = str(extra.get("disease_id", ""))
        if target_id not in valid_targets or disease_id not in valid_diseases:
            continue
        try:
            conn.execute(
                """INSERT OR IGNORE INTO target_disease_edges
                   (target_id, disease_id, association_score, evidence_type,
                    evidence_sources, confidence, retrieved_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    target_id,
                    disease_id,
                    extra.get("association_score"),
                    extra.get("evidence_type", "genetic_association"),
                    json.dumps(extra.get("evidence_sources", [])),
                    float(rec.get("confidence", 1.0)),
                    extra.get("retrieved_at"),
                ),
            )
            inserted += 1
        except Exception as e:
            logger.warning(
                "Failed to insert target-disease edge %s-%s: %s",
                target_id,
                disease_id,
                e,
            )
    conn.commit()
    logger.info("Loaded %d target-disease edges", inserted)
    return inserted


def load_drug_disease_edges(conn: sqlite3.Connection) -> int:
    edges_path = PROCESSED_DIR / "edges_drug_disease.jsonl"
    edges = _load_jsonl(edges_path)
    if not edges:
        logger.info("No drug-disease edges to load")
        return 0

    valid_drugs = _existing_ids(conn, "drugs")
    valid_diseases = _existing_ids(conn, "diseases")
    inserted = 0
    for edge in edges:
        extra = edge.get("extra", {})
        drug_id = str(extra.get("drug_id", ""))
        disease_id = str(extra.get("disease_id", ""))
        if drug_id not in valid_drugs or disease_id not in valid_diseases:
            continue
        try:
            conn.execute(
                """INSERT OR IGNORE INTO drug_disease_edges
                   (drug_id, disease_id, indication_type, evidence_source,
                    evidence_level, confidence, phase_context)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    drug_id,
                    disease_id,
                    extra.get("indication_type", "primary"),
                    extra.get("evidence_source", "curated_seed"),
                    extra.get("evidence_level", "unknown"),
                    float(edge.get("confidence", 1.0)),
                    extra.get("phase_context"),
                ),
            )
            inserted += 1
        except Exception as e:
            logger.warning(
                "Failed to insert drug-disease edge %s-%s: %s",
                drug_id,
                disease_id,
                e,
            )
    conn.commit()
    logger.info("Loaded %d drug-disease edges", inserted)
    return inserted


def load_drug_xrefs(conn: sqlite3.Connection) -> int:
    """Load drug cross-references from drug_xrefs.json."""
    xrefs_path = PROCESSED_DIR / "drug_xrefs.json"
    payload = _load_json(xrefs_path)
    xrefs = payload.get("xrefs", []) if isinstance(payload, dict) else payload
    if not xrefs:
        logger.info("No drug xrefs to load")
        return 0

    valid_drugs = _existing_ids(conn, "drugs")
    inserted = 0
    for xref in xrefs:
        drug_id = str(xref.get("drug_id", ""))
        if drug_id not in valid_drugs:
            continue
        try:
            conn.execute(
                """INSERT OR IGNORE INTO drug_xrefs
                   (drug_id, source_name, source_id, source_url, is_primary)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    drug_id,
                    xref.get("source_name"),
                    xref.get("source_id"),
                    xref.get("source_url"),
                    1 if xref.get("is_primary") else 0,
                ),
            )
            inserted += 1
        except Exception as e:
            logger.warning(
                "Failed to insert drug xref %s/%s: %s",
                drug_id,
                xref.get("source_name"),
                e,
            )
    conn.commit()
    logger.info("Loaded %d drug xrefs", inserted)
    return inserted


def load_target_xrefs(conn: sqlite3.Connection) -> int:
    """Load target cross-references from target_xrefs.json."""
    xrefs_path = PROCESSED_DIR / "target_xrefs.json"
    payload = _load_json(xrefs_path)
    xrefs = payload.get("xrefs", []) if isinstance(payload, dict) else payload
    if not xrefs:
        logger.info("No target xrefs to load")
        return 0

    valid_targets = _existing_ids(conn, "targets")
    inserted = 0
    for xref in xrefs:
        target_id = str(xref.get("target_id", ""))
        if target_id not in valid_targets:
            continue
        try:
            conn.execute(
                """INSERT OR IGNORE INTO target_xrefs
                   (target_id, source_name, source_id, source_url, is_primary)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    target_id,
                    xref.get("source_name"),
                    xref.get("source_id"),
                    xref.get("source_url"),
                    1 if xref.get("is_primary") else 0,
                ),
            )
            inserted += 1
        except Exception as e:
            logger.warning(
                "Failed to insert target xref %s/%s: %s",
                target_id,
                xref.get("source_name"),
                e,
            )
    conn.commit()
    logger.info("Loaded %d target xrefs", inserted)
    return inserted


def load_evidence_sources(conn: sqlite3.Connection) -> int:
    """Register all evidence sources used across extractions."""
    sources = [
        {
            "source_name": "Open Targets",
            "source_type": "database",
            "base_url": "https://www.opentargets.org",
            "version": "v4",
            "license": "CC BY-SA 4.0",
            "description": "Drug-target-disease associations",
        },
        {
            "source_name": "DGIdb",
            "source_type": "database",
            "base_url": "https://www.dgidb.org",
            "version": "v4",
            "license": "CC0",
            "description": "Drug-gene interaction database",
        },
        {
            "source_name": "DrugCentral",
            "source_type": "database",
            "base_url": "https://drugcentral.org",
            "version": "2021.09",
            "license": "CC BY 4.0",
            "description": "Drug-target interactions, bioactivities",
        },
        {
            "source_name": "TTD",
            "source_type": "database",
            "base_url": "https://db.idrblab.net/ttd",
            "version": "latest",
            "license": "academic",
            "description": "Therapeutic Target Database",
        },
        {
            "source_name": "ChEMBL",
            "source_type": "database",
            "base_url": "https://www.ebi.ac.uk/chembl",
            "version": "34",
            "license": "CC BY-SA 3.0",
            "description": "Bioactive molecules and drug discovery",
        },
        {
            "source_name": "KEGG",
            "source_type": "database",
            "base_url": "https://www.kegg.jp",
            "version": "latest",
            "license": "academic",
            "description": "Kyoto Encyclopedia of Genes and Genomes",
        },
        {
            "source_name": "PubChem",
            "source_type": "database",
            "base_url": "https://pubchem.ncbi.nlm.nih.gov",
            "version": "latest",
            "license": "public domain",
            "description": "Chemical substances and bioactivities",
        },
        {
            "source_name": "RxNorm",
            "source_type": "terminology",
            "base_url": "https://www.nlm.nih.gov/research/umls/rxnorm",
            "version": "latest",
            "license": "NLM",
            "description": "Drug naming and normalization",
        },
        {
            "source_name": "CTD",
            "source_type": "database",
            "base_url": "http://ctdbase.org",
            "version": "latest",
            "license": "public domain",
            "description": "Comparative Toxicogenomics Database",
        },
        {
            "source_name": "ClinicalTrials.gov",
            "source_type": "registry",
            "base_url": "https://clinicaltrials.gov",
            "version": "v2",
            "license": "public domain",
            "description": "Clinical trial registry",
        },
        {
            "source_name": "FDA",
            "source_type": "regulatory",
            "base_url": "https://www.fda.gov",
            "version": "latest",
            "license": "public domain",
            "description": "FDA drug approvals and labels",
        },
    ]

    inserted = 0
    for src in sources:
        try:
            conn.execute(
                """INSERT OR IGNORE INTO evidence_sources
                   (source_name, source_type, base_url, version, license, description)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    src["source_name"],
                    src["source_type"],
                    src["base_url"],
                    src["version"],
                    src["license"],
                    src["description"],
                ),
            )
            inserted += 1
        except Exception as e:
            logger.warning(
                "Failed to insert evidence source %s: %s", src["source_name"], e
            )
    conn.commit()
    logger.info("Loaded %d evidence sources", inserted)
    return inserted


def load_all(db_path: str) -> Dict[str, int]:
    """Full pipeline: migrate → seed → load edges/xrefs."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    counts: Dict[str, int] = {}

    logger.info("Running migrations...")
    run_migration(conn)

    logger.info("Seeding base tables...")
    counts["drugs_seeded"] = seed_drugs(conn)
    counts["diseases_seeded"] = seed_diseases(conn)
    counts["targets_seeded"] = seed_targets(conn)

    logger.info("Loading graph edges and cross-references...")
    counts["drug_target_edges"] = load_drug_target_edges(conn)
    counts["target_disease_edges"] = load_target_disease_edges(conn)
    counts["drug_disease_edges"] = load_drug_disease_edges(conn)
    counts["drug_xrefs"] = load_drug_xrefs(conn)
    counts["target_xrefs"] = load_target_xrefs(conn)
    counts["evidence_sources"] = load_evidence_sources(conn)

    # Summary
    for table in [
        "drugs",
        "diseases",
        "targets",
        "drug_target_edges",
        "target_disease_edges",
        "drug_disease_edges",
        "drug_xrefs",
        "target_xrefs",
        "evidence_sources",
    ]:
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        counts[f"total_{table}"] = row[0] if row else 0

    conn.close()
    logger.info("Done. Summary: %s", counts)
    return counts


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s - %(message)s"
    )
    parser = argparse.ArgumentParser(description="Load graph edges into SQLite")
    parser.add_argument("--db-path", default="drugtree.db", help="SQLite database path")
    args = parser.parse_args()

    counts = load_all(args.db_path)
    for k, v in counts.items():
        print(f"  {k}: {v}")
