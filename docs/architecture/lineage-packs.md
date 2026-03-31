# Lineage Packs Plan

This document defines a reusable curation plan for flagship therapeutic lineages in DrugTree. It aligns with existing architecture docs (`lineage-model.md`, `graph-schema.md`, `graph-transition-plan.md`) and is intended for curator-driven enrichment of `data/processed/lineage_edges.json` with auditable evidence.

## Lineage Pack Controlled Vocabulary

Use this edge/provenance vocabulary in every pack submission.

```text
EdgeType values (8):
- SAME_ACTIVE
- SAME_TARGET
- SAME_CLASS
- SAME_FAMILY
- DERIVED_FROM
- PRODRUG
- COMBINATION
- ME_TOO

Provenance hierarchy (high → low):
- PROVENANCE_LITERATURE
- PROVENANCE_REGULATORY
- PROVENANCE_DATABASE
- PROVENANCE_INFERRED
```

## Pack Template

Every therapeutic pack must be submitted with the following structure.

```yaml
pack_id: "<therapeutic_family_slug>"
title: "<display name>"
scope:
  atc_hint: ["<ATC prefixes>"]
  inclusion_rule: "Which drugs are in-scope"
  exclusion_rule: "What is out-of-scope"
representative_drugs:
  - "<generic name>"
mechanism_summary:
  primary_target_or_pathway: "<target/pathway>"
  mechanism_statement: "Short pharmacology statement"
expected_edge_types:
  required: ["SAME_TARGET", "SAME_CLASS"]
  optional: ["DERIVED_FROM", "ME_TOO", "PRODRUG", "COMBINATION", "SAME_ACTIVE", "SAME_FAMILY"]
evidence_plan:
  preferred_sources:
    - provenance: "PROVENANCE_REGULATORY"
      examples: ["FDA labels", "EMA EPAR"]
    - provenance: "PROVENANCE_LITERATURE"
      examples: ["peer-reviewed reviews", "trial publications"]
    - provenance: "PROVENANCE_DATABASE"
      examples: ["ChEMBL", "DrugBank", "KEGG", "PubChem"]
  rationale_tags: ["MECHANISM_OF_ACTION", "PHARMACOLOGICAL_SIMILARITY", "REGULATORY_APPROVAL", "CLINICAL_GUIDELINE", "STRUCTURAL_SIMILARITY", "FORMULATION_RELATIONSHIP"]
quality_targets:
  minimum_edges: <int>
  minimum_confidence: <0.0-1.0>
  provenance_diversity_min: <int>
  temporal_coverage_min_years: <int>
known_gaps:
  - "Missing drugs/edges/evidence to curate"
reviewers:
  primary: "<curator>"
  secondary: "<reviewer>"
```

## Curation Workflow (review → evidence → merge)

| Phase | Objective | Required Actions | Deliverable |
|---|---|---|---|
| Review | Bound the lineage and enumerate candidate drugs/edges | Define pack scope, list representatives, scan current lineage/family artifacts for existing edges and obvious holes | Draft pack YAML + candidate edge table |
| Evidence | Attach provenance-backed support for each proposed edge | For each edge: capture source URL, provenance level, rationale tags, confidence (0.0-1.0), and notes about directionality | Evidence matrix ready for import |
| Merge | Land curated edges with auditability | Resolve conflicts, apply precedence by provenance hierarchy, run DAG/validation checks, record change summary | Updated lineage artifacts + review log |

Operational rules:
1. Prefer high-grade evidence first (regulatory/literature), then database, then inferred.
2. Keep directionality explicit for `DERIVED_FROM`, `PRODRUG`, and `COMBINATION` edges.
3. Any confidence <0.70 requires explicit reviewer note before merge.
4. Reject ambiguous synonym-only matches until identity is normalized.

## Flagship Pack 1: Statins

| Field | Plan |
|---|---|
| Representative drugs | atorvastatin, simvastatin, rosuvastatin, pravastatin, lovastatin, fluvastatin, pitavastatin |
| Key mechanisms | Competitive inhibition of HMG-CoA reductase (cholesterol biosynthesis blockade); LDL-C lowering via upregulated hepatic LDL receptor activity |
| Expected edge types | Required: `SAME_TARGET`, `SAME_CLASS`; Frequent: `ME_TOO`, `SAME_FAMILY`; Optional: `DERIVED_FROM`, `COMBINATION` |
| Data sources | FDA/EMA labels and monographs (PROVENANCE_REGULATORY); guideline and review literature (PROVENANCE_LITERATURE); ChEMBL/DrugBank/KEGG/PubChem mappings (PROVENANCE_DATABASE) |
| Known gaps | Sparse explicit lineage beyond core pairs in current processed edges; incomplete mapping of salt/formulation variants to `SAME_ACTIVE`; weak chronology notes for older entries |

## Flagship Pack 2: EGFR Inhibitors

| Field | Plan |
|---|---|
| Representative drugs | erlotinib, gefitinib, afatinib, osimertinib, dacomitinib, necitumumab |
| Key mechanisms | EGFR pathway inhibition: small-molecule TKIs (reversible/irreversible ATP-site inhibition) plus anti-EGFR monoclonal antibody blockade |
| Expected edge types | Required: `SAME_TARGET`, `SAME_CLASS`; Frequent: `ME_TOO`, `SAME_FAMILY`; Optional: `DERIVED_FROM`, `COMBINATION` |
| Data sources | Regulatory labels with mutation/context indications (PROVENANCE_REGULATORY); resistance-mechanism and sequencing literature (PROVENANCE_LITERATURE); curated target databases (PROVENANCE_DATABASE) |
| Known gaps | Need clean subtype handling between TKIs and antibody modality; expected missing edges for later-generation resistance-oriented agents; combination-therapy links under-modeled |

## Flagship Pack 3: CDK4/6 Inhibitors

| Field | Plan |
|---|---|
| Representative drugs | palbociclib, ribociclib, abemaciclib, trilaciclib |
| Key mechanisms | Inhibition of cyclin-dependent kinases 4 and 6 to arrest G1→S transition; oncology use plus myelopreservation context for trilaciclib |
| Expected edge types | Required: `SAME_TARGET`, `SAME_CLASS`; Frequent: `ME_TOO`, `SAME_FAMILY`; Optional: `COMBINATION`, `DERIVED_FROM` |
| Data sources | FDA/EMA labeling and indication updates (PROVENANCE_REGULATORY); clinical-trial and resistance literature (PROVENANCE_LITERATURE); target/pathway databases (PROVENANCE_DATABASE) |
| Known gaps | Limited existing lineage edges in processed graph; inconsistent representation of class-level relation vs indication-specific behavior; combination context needs explicit edge capture |

## Flagship Pack 4: PARP Inhibitors

| Field | Plan |
|---|---|
| Representative drugs | olaparib, rucaparib, niraparib, talazoparib |
| Key mechanisms | PARP1/2 inhibition causing impaired single-strand DNA repair and synthetic lethality in homologous-recombination deficient tumors |
| Expected edge types | Required: `SAME_TARGET`, `SAME_CLASS`; Frequent: `ME_TOO`, `SAME_FAMILY`; Optional: `COMBINATION`, `DERIVED_FROM` |
| Data sources | Regulatory approvals and label expansions by tumor biomarker context (PROVENANCE_REGULATORY); trial/publication corpus on BRCA/HRD settings (PROVENANCE_LITERATURE); ChEMBL/DrugBank target links (PROVENANCE_DATABASE) |
| Known gaps | Underlinked cross-indication edges (ovarian/breast/prostate/pancreatic settings); biomarker context absent in many edge notes; chronology and rationale tags often incomplete |

## Flagship Pack 5: Cephalosporins

| Field | Plan |
|---|---|
| Representative drugs | 1st-5th generation anchors: cefazolin, cefuroxime, ceftriaxone, cefepime, ceftaroline |
| Key mechanisms | Beta-lactam inhibition of bacterial cell-wall synthesis through penicillin-binding proteins, with generation-dependent spectrum and resistance profile shifts |
| Expected edge types | Required: `SAME_CLASS`, `SAME_FAMILY`; Frequent: `ME_TOO`, `DERIVED_FROM`; Optional: `SAME_ACTIVE`, `PRODRUG`, `COMBINATION` |
| Data sources | Regulatory labels and antimicrobial spectra (PROVENANCE_REGULATORY); infectious disease literature and stewardship references (PROVENANCE_LITERATURE); ATC/DrugBank/ChEMBL/PubChem mappings (PROVENANCE_DATABASE) |
| Known gaps | Generation tagging not consistently encoded in lineage rationale; many salt/prodrug forms need explicit `SAME_ACTIVE`/`PRODRUG`; broad class has high risk of overconnecting without evidence |

## Quality Gates

All flagship packs must pass every gate before merge.

| Gate | Threshold | Pass Criteria |
|---|---|---|
| Minimum edge count | >= 12 curated candidate edges per pack | Candidate table includes at least 12 non-duplicate edges linked to representative drugs |
| Provenance diversity | >= 3 provenance levels present | Pack includes evidence from at least 3 of: LITERATURE, REGULATORY, DATABASE, INFERRED |
| Temporal coverage | >= 15-year approval span (or documented exception) | Earliest vs latest approved representative in pack meets span, or reviewer-approved exception recorded |
| Confidence floor | >= 0.70 for merge-ready edges | All merged edges meet floor; lower scores remain in review backlog |
| Required type coverage | 100% of required edge types represented | Each pack has at least one accepted edge for every required type listed in pack plan |
| Evidence traceability | 100% edges have source URL or citation key | Every merged edge includes reproducible provenance pointer |

## Merge Readiness Checklist

- Pack template fully filled and peer-reviewed.
- Candidate edges satisfy quality gates.
- Provenance precedence conflicts resolved.
- Notes include rationale tags and concise mechanism justification.
- Change log entry prepared for audit trail.
