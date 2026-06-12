# Disease Reasoning Plan

Plan for improving disease hierarchy semantics, orphan handling, region-aware display, and strict edge-backed disease→drug filtering.

> Canonical inputs: `data/diseases.json` (50 diseases), `data/disease_drug_edges.json` (64 edges), `data/ontology/body-ontology.json` (14 regions), and `src/backend/models/disease.py`.
>
> Hard constraint: **Do not infer anatomy solely from body-region coincidence where explicit disease-drug edges exist.**

## Reference model and ontology primitives

Disease reasoning must use model fields already present in `Disease`:

- Identity: `id`, `canonical_name`, `synonyms[]`
- Anatomy: `body_region`, `anatomy_nodes[]`
- Rarity: `orphan_flag`, `prevalence_tier`, `prevalence_count`
- Evidence: `evidence_level`, `mechanism_summary`, `mechanism_citation`
- Counts: `target_count`, `approved_drug_count`, `clinical_drug_count`
- External IDs: `orphanet_id`, `mondo_id`, `doid_id`, `mesh_id`, `efo_id`, `icd10_code`

Body ontology (`body-ontology.json`) fields used by display logic:

- `visible_regions[]` (`id`, `display_name`, `icon`, `description`, `internal_nodes[]`)
- `internal_ontology` (anatomy node dictionary + optional `parent`)
- `disease_to_anatomy` (`region`, `nodes[]`) for canonical placement defaults
- `placement_authority` for fallback rationale ordering

Current data reality to preserve while improving semantics:

- 17 diseases have `orphan_flag=true`.
- `systemic_multiorgan` is used heavily (15 diseases), including several sparse entries.
- All 50 diseases currently have at least one edge in `disease_drug_edges.json`.

---

## 1) Disease Grouping Semantics

### 1.1 Multi-axis grouping (ordered)

Disease grouping should use four axes in parallel:

1. **Anatomy anchor axis**: `body_region` + `anatomy_nodes[]`.
2. **Clinical/mechanistic axis**: `categories[]`, `mechanism_summary`, target context.
3. **Population axis**: `prevalence_tier`, `orphan_flag`, `prevalence_count`.
4. **Evidence axis**: `evidence_level` + edge evidence rollups.

`body_region` remains the atlas anchor, but not the sole semantic classifier.

### 1.2 Body-region semantics

- Primary placement comes from `disease.body_region`.
- Fine placement comes from `anatomy_nodes[]` mapped into `internal_ontology[body_region]`.
- Keep mapping deterministic even when disease meaning is cross-system.

Examples:

- `glioma` → `brain_cns`, nodes `brain`, `cerebrum`.
- `type_2_diabetes` → `endocrine_metabolic`, nodes `pancreatic_endocrine`, `adipose_metabolic_system`.

### 1.3 Therapeutic/mechanistic grouping

Use `categories[]` as an orthogonal grouping layer (chips/subgroups/navigation), not as replacement for anatomy anchor.

Examples from current dataset:

- `hyperlipidemia`: `cardiovascular`, `metabolic`, `chronic`.
- `crohns_disease`: `gastrointestinal`, `autoimmune`, `orphan`, `chronic`.
- `retinoblastoma`: `cancer`, `orphan`, `pediatric`, `sensory`.
- `psoriasis`: `dermatological`, `autoimmune`, `chronic`, `inflammatory`.

### 1.4 Cross-region semantics

Cross-region diseases require a primary/secondary model:

- **Primary**: exactly one `body_region` (deterministic atlas anchoring).
- **Secondary**: additional anatomy footprint from `anatomy_nodes`, categories, and mechanism cues.

Examples:

- `hyperlipidemia` is anchored in `heart_vascular` but includes `systemic_multiorgan_core`.
- `diabetic_retinopathy` is anchored in `eye_ear` with secondary vascular node `blood_vessels`.
- `systemic_lupus_erythematosus` is explicitly `systemic_multiorgan` with `immune_system` + systemic core nodes.

### 1.5 Parent-child hierarchy rules

For consistent rendering (region → disease → drug tree), define hierarchy parents as:

1. Region root = `body_region`.
2. Optional category subgroup = normalized major category (`cancer`, `autoimmune`, `metabolic`, etc.).
3. Disease leaf = `id`.
4. Drug leaves = explicit edge-derived drugs only.

Tie-breakers for multi-category diseases:

- Prefer domain categories over modifiers (`orphan`, `chronic`) as primary subgroup.
- Keep modifier categories as badges/chips.
- If no categories, place disease under region `uncategorized` bucket.

---

## 2) Orphan Disease Treatment

### 2.1 Orphan classification trust order

Use this precedence:

1. `orphan_flag` (authoritative runtime flag)
2. `prevalence_tier in {ultra_rare, rare}` (consistency cross-check)
3. `orphanet_id` existence (reference enrichment signal)

### 2.2 Display behavior

- Keep `ORPHAN` badge highly visible in disease list rows and selected disease chip.
- Show prevalence text adjacent to badge (`Ultra-rare`, `Rare`, or count).
- In detail panel, place `orphanet_id` and `mondo_id` near badge for immediate provenance.

### 2.3 Inclusion defaults

“Interesting diseases” default set should include:

- all `orphan_flag=true` diseases; and
- a small set of high-impact non-orphan anchors (`type_2_diabetes`, `alzheimers_disease`, `hypertension`, etc.).

### 2.4 Sorting policy for orphan-focused lists

Sort by:

1. `prevalence_tier` (`ultra_rare` → `rare` → `uncommon` → `common` → `unknown`)
2. ascending `prevalence_count` when present
3. descending evidence weight
4. `canonical_name`

### 2.5 External references

- Render all present external IDs (`orphanet_id`, `mondo_id`, `doid_id`, `mesh_id`, `efo_id`, `icd10_code`).
- Prioritize Orphanet + MONDO links for orphan diseases.
- If IDs are missing, hide missing-link UI rather than showing placeholders.

---

## 3) Region-Aware Display Logic

### 3.1 Highlight trigger rules

When disease is selected:

- highlight `anatomy_nodes[]` first;
- if `anatomy_nodes[]` is empty, highlight by `body_region` anchor only;
- render label using ontology `display_name` (not raw region ID).

When drug is selected:

- do not auto-infer disease-region highlighting from shared region;
- keep disease highlighting tied to active disease state.

### 3.2 Multi-disease-per-region clutter control

For dense regions (e.g., `systemic_multiorgan`):

- show region-level count badges (e.g., `Systemic/Multi-organ: 15`);
- collapse disease list by default with ranked reveal;
- keep map highlight at region level unless user selects a specific disease.

### 3.3 Cross-region display for systemic diseases

- Primary visual emphasis stays on primary `body_region`.
- Secondary footprints are shown as subtle linked markers or tooltips.
- Tooltip format: `Primary: <region>; Secondary anatomy: <node list>`.

### 3.4 Region label formatting

- Preferred: `{Disease Canonical Name} · {Region Display Name}`.
- Include region icon from `visible_regions.icon` where available.
- Avoid raw IDs like `heart_vascular` in user-facing labels.

---

## 4) Edge-Backed Filtering Rules

### 4.1 Canonical disease→drug rule

Always resolve disease drugs from explicit edges:

- `DrugSet(disease_id) = { edge.drug_id | edge.disease_id == disease_id }`
- Disease-filtered grid = `DrugSet(disease_id)` intersected with active non-disease filters.

### 4.2 Explicit non-inference rules

Never derive disease-drug association from:

- shared `body_region`
- shared `anatomy_nodes`
- shared `categories`
- shared therapeutic area proxies

These can support navigation hints, not association truth.

### 4.3 Zero-edge disease behavior

If a disease ever has zero explicit edges:

- return empty associated-drug set;
- keep disease searchable/selectable;
- show explicit “No explicit drug associations yet” state;
- optionally show mechanism/target exploration hints in a separate block.

### 4.4 Evidence-level weighting for display priority

Drug ranking within disease panels should use edge evidence order:

`approved > phase_iii > phase_ii > phase_i > preclinical > hypothesized > unknown`

Tie-break by confidence (if present), then deterministic label sort.

### 4.5 Concrete current examples

- `glioma` → `temozolomide` (approved)
- `hypertension` → `lisinopril`, `losartan-potassium`, `metoprolol-succinate`, `atenolol`
- `systemic_lupus_erythematosus` → `prednisone`
- shared-drug case: `methotrexate-sodium` links `lymphoma`, `crohns_disease`, `ulcerative_colitis`, `psoriasis`, `breast_cancer`

---

## 5) Future Improvements

### 5.1 Target-based disease grouping
- Add target-neighborhood grouping using `target_count` and target overlap.
- Provide optional target-cluster browsing without changing edge-backed filtering.

### 5.2 Mechanism-based cross-region navigation
- Build cross-region “related by mechanism” rails from `mechanism_summary` + category patterns.
- Keep these as navigation suggestions, not inferred disease-drug associations.

### 5.3 Disease similarity scoring
- Add an explainable `0..1` similarity score based on category overlap, target overlap, shared-drug overlap, ontology-node proximity, and prevalence proximity.
- Use this only for recommendations/ranking, not for replacing explicit edges.

### 5.4 Data quality and UI upgrades
- Validate consistency of `orphan_flag`, `prevalence_tier`, and `prevalence_count`.
- Validate `anatomy_nodes[]` against ontology internal node catalogs.
- Prioritize curation of sparse systemic entries with empty `anatomy_nodes`.
- Add mode toggle (`Region View` vs `Mechanism View`), orphan spotlight preset, and edge-evidence chips.
