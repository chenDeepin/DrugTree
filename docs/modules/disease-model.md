# Disease Model

Defines the disease entity, drug-disease relationships, target associations, prevalence classification, and evidence levels.

> **Source of truth**: `src/backend/models/disease.py`, `data/diseases.json`, `data/disease_drug_edges.json`

---

## Table of Contents

1. [Overview](#1-overview)
2. [Disease Model](#2-disease-model)
3. [Target Model](#3-target-model)
4. [Drug-Disease Edge Model](#4-drug-disease-edge-model)
5. [Prevalence Tiers](#5-prevalence-tiers)
6. [Evidence Levels](#6-evidence-levels)
7. [Indication Types](#7-indication-types)
8. [External Ontology IDs](#8-external-ontology-ids)
9. [Disease Universe Statistics](#9-disease-universe-statistics)
10. [Body Region Mapping](#10-body-region-mapping)

---

## 1. Overview

DrugTree models 50 diseases with explicit drug-disease edges, prevalence data, and links to external ontologies. The disease model supports:

- **Hierarchical browsing**: disease categories with parent-child relationships
- **Edge-backed filtering**: drugs are linked to diseases via explicit edges, not inferred from body-region coincidence
- **Orphan disease flagging**: rare/ultra-rare diseases are flagged for prominence
- **Evidence tracking**: each drug-disease relationship carries evidence level and indication type

### Canonical Data Sources

| File | Content |
|------|---------|
| `data/diseases.json` | 50 diseases with metadata |
| `data/disease_drug_edges.json` | Drug ↔ disease relationships with evidence |
| `data/ontology/body-ontology.json` | Body region definitions and anatomy mapping |

---

## 2. Disease Model

Full schema from `src/backend/models/disease.py`:

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Unique identifier (e.g., `glioma`) |
| `canonical_name` | `str` | Canonical disease name (e.g., `Glioma`) |
| `body_region` | `str` | Primary body region ID (e.g., `brain_cns`) |

### Optional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `synonyms` | `List[str]` | `[]` | Alternative names |
| `anatomy_nodes` | `List[str]` | `[]` | Specific anatomy nodes within region |
| `orphan_flag` | `bool` | `False` | True if ultra-rare or rare disease |
| `prevalence_tier` | `PrevalenceTier` | `unknown` | Prevalence classification |
| `prevalence_count` | `int` | `null` | Estimated global patient count |
| `evidence_level` | `EvidenceLevel` | `unknown` | Overall evidence strength |
| `mechanism_summary` | `str` | `null` | 2–3 sentence mechanism explanation |
| `mechanism_citation` | `str` | `null` | Citation for mechanism (DOI/PMID) |
| `target_count` | `int` | `0` | Number of associated targets |
| `approved_drug_count` | `int` | `0` | Number of approved drugs |
| `clinical_drug_count` | `int` | `0` | Number of drugs in clinical trials |
| `orphanet_id` | `str` | `null` | Orphanet disease identifier |
| `mondo_id` | `str` | `null` | MONDO ontology ID |
| `doid_id` | `str` | `null` | Disease Ontology ID |
| `mesh_id` | `str` | `null` | MeSH disease identifier |
| `efo_id` | `str` | `null` | Experimental Factor Ontology ID |
| `icd10_code` | `str` | `null` | ICD-10 code |

### Graph Node

When resolved through the graph query service, diseases appear as `GraphNodeRef`:

```python
GraphNodeRef(
    node_id="disease:glioma",
    node_type=GraphNodeType.disease,
    label="Glioma",
    extra={
        "body_region": "brain_cns",
        "categories": [...]
    }
)
```

---

## 3. Target Model

Targets represent molecular entities (proteins, receptors) associated with diseases.

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `str` | Yes | Unique target identifier (e.g., `EGFR`) |
| `symbol` | `str` | Yes | Gene/protein symbol |
| `name` | `str` | Yes | Full target name |
| `modality` | `Modality` | No | Target modality (default: `unknown`) |
| `disease_ids` | `List[str]` | No | Associated disease IDs |
| `uniprot_id` | `str` | No | UniProt ID |
| `hgnc_id` | `str` | No | HGNC gene ID |
| `entrez_id` | `int` | No | Entrez Gene ID |

### Target Modality

```python
class Modality(str, Enum):
    INHIBITOR = "inhibitor"
    ACTIVATOR = "activator"
    AGONIST = "agonist"
    ANTAGONIST = "antagonist"
    MODULATOR = "modulator"
    BLOCKER = "blocker"
    UNKNOWN = "unknown"
```

---

## 4. Drug-Disease Edge Model

Explicit relationships between drugs and diseases. These are the **canonical** links used for disease-based filtering — NOT inferred from shared body regions.

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `drug_id` | `str` | Yes | Drug identifier |
| `disease_id` | `str` | Yes | Disease identifier |
| `indication_type` | `IndicationType` | No | Type of indication (default: `primary`) |
| `evidence_source` | `str` | Yes | Evidence source (e.g., `FDA`, `NCT123456`) |
| `evidence_level` | `EvidenceLevel` | No | Evidence strength (default: `unknown`) |
| `confidence` | `float` | No | Confidence score 0–1 (default: `1.0`) |
| `phase_context` | `str` | No | Clinical trial phase context |

### Edge ID Convention

Disease-drug edges use the format: `disease:{disease_id}_drug:{drug_id}`

Example: `disease:glioma_drug:temozolomide`

---

## 5. Prevalence Tiers

```python
class PrevalenceTier(str, Enum):
    ULTRA_RARE = "ultra_rare"   # < 10K patients globally
    RARE = "rare"               # 10K–100K patients globally
    UNCOMMON = "uncommon"       # 100K–1M patients globally
    COMMON = "common"           # > 1M patients globally
    UNKNOWN = "unknown"
```

Diseases flagged as `ultra_rare` or `rare` automatically set `orphan_flag = true`.

---

## 6. Evidence Levels

Strength of evidence supporting drug-disease relationships:

```python
class EvidenceLevel(str, Enum):
    APPROVED = "approved"         # Regulatory approval
    PHASE_III = "phase_iii"       # Phase III clinical trial
    PHASE_II = "phase_ii"         # Phase II clinical trial
    PHASE_I = "phase_i"           # Phase I clinical trial
    PRECLINICAL = "preclinical"   # Preclinical data only
    HYPOTHESIZED = "hypothesized" # Computational/biological hypothesis
    UNKNOWN = "unknown"
```

---

## 7. Indication Types

Type of drug-disease indication:

```python
class IndicationType(str, Enum):
    PRIMARY = "primary"               # Primary approved indication
    ADJUVANT = "adjuvant"             # Used with primary treatment
    NEOADJUVANT = "neoadjuvant"       # Before primary treatment
    MAINTENANCE = "maintenance"       # Long-term disease control
    PALLIATIVE = "palliative"         # Symptom relief
    OFF_LABEL = "off_label"           # Off-label use with evidence
    INVESTIGATIONAL = "investigational" # Under investigation
```

---

## 8. External Ontology IDs

DrugTree diseases link to external ontologies for interoperability:

| Ontology | Field | Example | Source |
|----------|-------|---------|--------|
| Orphanet | `orphanet_id` | `ORPHA314` | [orpha.net](https://www.orpha.net) |
| MONDO | `mondo_id` | `MONDO:0018157` | [mondo.monarchinitiative.org](https://mondo.monarchinitiative.org) |
| Disease Ontology | `doid_id` | `DOID:3116` | [disease-ontology.org](http://www.disease-ontology.org) |
| MeSH | `mesh_id` | `D005919` | [meshb.nlm.nih.gov](https://meshb.nlm.nih.gov) |
| EFO | `efo_id` | `EFO:0000552` | [www.ebi.ac.uk/efo](https://www.ebi.ac.uk/efo) |
| ICD-10 | `icd10_code` | `C71.9` | [icd.who.int](https://icd.who.int) |

---

## 9. Disease Universe Statistics

The `DiseaseUniverseStats` model provides aggregate counts:

| Field | Description |
|-------|-------------|
| `total_diseases` | Total diseases in database |
| `orphan_diseases` | Orphan disease count |
| `total_targets` | Total targets |
| `total_approved_drugs` | Total approved drugs |
| `total_clinical_drugs` | Total drugs in clinical trials |
| `diseases_by_region` | Disease counts by body region |
| `diseases_by_prevalence` | Disease counts by prevalence tier |

---

## 10. Body Region Mapping

Each disease maps to a primary body region from the body ontology (`data/ontology/body-ontology.json`).

### Critical Constraint

> **Disease filtering must use explicit edge-linked `drug_id`s from `data/disease_drug_edges.json`, not same-body-region inference.**

When a user selects a disease in the UI:
1. Look up the disease's `drug_id`s from `disease_drug_edges.json`
2. Filter the drug grid to those exact IDs
3. Do NOT fall back to "all drugs in this body region"

This constraint ensures accurate disease-drug associations even when multiple diseases share the same body region.
