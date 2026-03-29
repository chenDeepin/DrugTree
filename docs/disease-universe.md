# Disease Universe - Navigation and Data Model

> **Version**: 1.1.0
> **Last Updated**: 2026-03-14
> **Author**: DrugTree Team

---

## Overview

The Disease Universe is the core navigation paradigm for DrugTree. It enables a **disease-first exploration workflow** where users navigate from body regions to diseases, then to specific drugs. This document defines the data model, navigation logic, multi-filter support, and orphan drug/disease handling.

---

## Quick Navigation Example

**User wants to find drugs for eye cancers:**

```
Step 1: Select Body Region → Eye
        Shows: Glaucoma, Uveal Melanoma, Retinoblastoma, Conjunctivitis, Diabetic Retinopathy

Step 2: Add Category Filter → Cancer
        Shows: Uveal Melanoma, Retinoblastoma (only eye + cancer diseases)

Step 3: Select Disease → Uveal Melanoma
        Shows: Imatinib, Pembrolizumab, Nivolumab (drugs for this orphan disease)
```

---

## Navigation Paradigm

### User Flow: Body Region → Disease → Drug

```
┌─────────────────────────────────────────────────────────────┐
│  Step 1: Select Body Region                                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │   Eye    │ │  Lung    │ │  Heart   │ │  Blood   │ ...   │
│  │   👁️     │ │   🫁     │ │   ❤️     │ │   🩸     │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
│                           ↓                                  │
├─────────────────────────────────────────────────────────────┤
│  Step 2: Select Disease(s) from Region                      │
│  ┌────────────────────┐  ┌────────────────────┐            │
│  │ Eye Diseases (3)   │  │ + Additional Filter │            │
│  │ ├─ Glaucoma        │  │ [Cancer] ☑         │            │
│  │ ├─ Cataracts       │  │                    │            │
│  │ └─ Eye Melanoma*   │  │ Result: Eye Cancer │            │
│  │    (orphan)        │  │ (1 disease)        │            │
│  └────────────────────┘  └────────────────────┘            │
│                           ↓                                  │
├─────────────────────────────────────────────────────────────┤
│  Step 3: View Associated Drugs                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Drugs for Eye Melanoma (3 drugs)                     │  │
│  │                                                       │  │
│  │ ┌─────────┐ ┌─────────┐ ┌─────────┐                 │  │
│  │ │Tebentafu│ │Pembroliz│ │Nivolumab│                 │  │
│  │ │  (2022) │ │  (2020) │ │  (2020) │                 │  │
│  │ └─────────┘ └─────────┘ └─────────┘                 │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘

* Orphan drug indicator shown
```

---

## Multi-Filter Logic

### Filter Types

1. **Primary Filter**: Body Region (mutually exclusive)
   - User selects ONE body region at a time
   - Shows all diseases in that region

2. **Secondary Filters**: Disease Categories (stackable, AND logic)
   - Cancer types
   - Infectious diseases
   - Autoimmune diseases
   - Orphan diseases
   - Chronic diseases

### Multi-Filter Behavior (AND Logic)

```javascript
// PSEUDOCODE: Multi-filter logic
function applyFilters(bodyRegion, diseaseCategories) {
  // Step 1: Get all diseases in body region
  let diseases = getDiseasesByBodyRegion(bodyRegion);
  
  // Step 2: Apply disease category filters (AND logic)
  if (diseaseCategories.length > 0) {
    diseases = diseases.filter(disease => 
      diseaseCategories.every(category => 
        disease.categories.includes(category)
      )
    );
  }
  
  // Step 3: Get all drugs for filtered diseases
  const drugs = diseases.flatMap(disease => 
    getDrugsForDisease(disease.id)
  );
  
  return { diseases, drugs };
}
```

### Example: Eye + Cancer Filter

| Body Region | Disease Category | Result |
|-------------|------------------|--------|
| Eye | (none) | Glaucoma, Uveal Melanoma, Retinoblastoma, Conjunctivitis, Diabetic Retinopathy |
| Eye | Cancer | **Uveal Melanoma, Retinoblastoma** (eye + cancer diseases) |
| Eye | Cancer + Orphan | **Uveal Melanoma, Retinoblastoma** (both are orphan cancers) |
| Eye | Orphan | Uveal Melanoma, Retinoblastoma (orphan diseases) |
| Eye | Infectious | Conjunctivitis (infectious eye disease) |
| Eye | Metabolic | Diabetic Retinopathy (metabolic eye disease) |

### Multi-Filter Implementation Details

The AND logic is strict - diseases must have **ALL** selected categories:

```javascript
// CORRECT: Multi-filter with AND logic
function applyCategoryFilters(diseases, selectedCategories) {
  if (selectedCategories.length === 0) return diseases;
  
  return diseases.filter(disease => 
    selectedCategories.every(category => 
      disease.categories.includes(category)
    )
  );
}

// Example: Eye + Cancer + Orphan
// Result: Uveal Melanoma (has cancer AND orphan)
//         Retinoblastoma (has cancer AND orphan)
// NOT: Glioma (cancer but different body region)
// NOT: CML (cancer + orphan but blood, not eye)
```

---

## Disease Categories

Diseases are tagged with multiple categories to enable flexible filtering:

### Category Tags

| Category | Description | Examples |
|----------|-------------|----------|
| `cancer` | Malignant neoplasms | Lung cancer, Breast cancer, Glioma |
| `infectious` | Bacterial, viral, fungal, parasitic | Pneumonia, Tuberculosis, Hepatitis |
| `autoimmune` | Autoimmune disorders | Lupus, Crohn's, Ulcerative Colitis |
| `cardiovascular` | Heart and vascular diseases | Hypertension, Heart failure |
| `metabolic` | Metabolic disorders | Type 2 diabetes, Hyperlipidemia |
| `neurological` | Nervous system disorders | Alzheimer's, Epilepsy, Parkinson's |
| `respiratory` | Lung/airway diseases | Asthma, COPD |
| `orphan` | Rare diseases (<200K patients) | CML, Crohn's, Eye Melanoma |
| `chronic` | Long-term conditions | Diabetes, Hypertension, COPD |
| `acute` | Sudden onset conditions | Pneumonia, Infection |

### Disease Schema with Categories

```json
{
  "id": "eye_melanoma",
  "canonical_name": "Uveal Melanoma",
  "synonyms": ["Ocular melanoma", "Choroidal melanoma"],
  "body_region": "eye_ear",
  "anatomy_nodes": ["eye", "choroid", "iris"],
  "orphan_flag": true,
  "categories": ["cancer", "orphan"],
  "prevalence_tier": "rare",
  "prevalence_count": 7000,
  "evidence_level": "approved",
  "target_count": 5,
  "approved_drug_count": 3,
  "clinical_drug_count": 8
}
```

---

## Orphan Drug/Disease Support

### Orphan Disease Definition

An **orphan disease** (rare disease) affects fewer than 200,000 people in the United States (or <1 in 2,000 in Europe).

### Orphan Drug Definition

An **orphan drug** is developed specifically to treat an orphan disease. These drugs receive special regulatory incentives (market exclusivity, tax credits, grants).

### Orphan Display Rules

#### In Disease List
```html
<!-- Orphan diseases show badge -->
<div class="disease-card">
  <span class="disease-name">Eye Melanoma</span>
  <span class="orphan-badge">🦓 Orphan</span>
  <span class="drug-count">3 drugs</span>
</div>
```

#### In Drug List
```html
<!-- Orphan drugs show indicator -->
<div class="drug-card">
  <span class="drug-name">Tebentafusp</span>
  <span class="orphan-indicator">🦓 Orphan Drug</span>
  <span class="indication">Eye Melanoma (orphan)</span>
</div>
```

### Orphan Database

```json
{
  "orphan_diseases": [
    {
      "id": "eye_melanoma",
      "name": "Uveal Melanoma",
      "prevalence_count": 7000,
      "orphan_designation_year": 2020,
      "drugs": ["tebentafusp", "pembrolizumab", "nivolumab"]
    },
    {
      "id": "cml",
      "name": "Chronic Myeloid Leukemia",
      "prevalence_count": 70000,
      "orphan_designation_year": 2001,
      "drugs": ["imatinib", "dasatinib", "nilotinib", "bosutinib", "ponatinib"]
    },
    {
      "id": "crohns_disease",
      "name": "Crohn's Disease",
      "prevalence_count": 800000,
      "orphan_designation_year": 1998,
      "drugs": ["infliximab", "adalimumab", "ustekinumab", "vedolizumab"]
    }
  ]
}
```

---

## Data Model

### Body Region Schema

```json
{
  "id": "eye_ear",
  "display_name": "Eye / Ear",
  "icon": "👁️",
  "description": "Sensory organ drugs",
  "internal_nodes": ["eye", "retina", "cornea", "ear", "inner_ear"],
  "disease_count": 5,
  "drug_count": 28
}
```

### Disease Schema (Enhanced)

```json
{
  "id": "disease_id",
  "canonical_name": "Disease Name",
  "synonyms": ["Synonym 1", "Synonym 2"],
  "body_region": "body_region_id",
  "anatomy_nodes": ["node1", "node2"],
  "orphan_flag": false,
  "categories": ["cancer", "chronic"],
  "prevalence_tier": "common|uncommon|rare",
  "prevalence_count": 1000000,
  "evidence_level": "approved|clinical|preclinical",
  "target_count": 10,
  "approved_drug_count": 15,
  "clinical_drug_count": 8,
  "drugs": ["drug_id_1", "drug_id_2"]
}
```

### Drug Schema (Enhanced with Disease Link)

```json
{
  "id": "drug_id",
  "name": "Drug Name",
  "smiles": "...",
  "inchikey": "...",
  "atc_code": "C10AA05",
  "atc_category": "C",
  "molecular_weight": 558.64,
  "phase": "IV",
  "year_approved": 1996,
  "generation": 2,
  "indication": "Primary indication",
  "targets": ["Target 1", "Target 2"],
  "company": "Company Name",
  "synonyms": ["Brand 1", "Brand 2"],
  "class": "Drug Class",
  "body_regions": ["heart_vascular", "blood_immune"],
  "diseases": ["hypertension", "hyperlipidemia"],
  "orphan_flag": false,
  "orphan_disease_ids": []
}
```

---

## Navigation State Machine

### State Transitions

```
┌─────────────────────────────────────────────────────────┐
│                    Navigation States                     │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  [DEFAULT]                                               │
│  State: { bodyRegion: null, categories: [], diseases: [] }│
│  View: All body regions highlighted                     │
│                                                          │
│         ↓ selectBodyRegion(region)                      │
│                                                          │
│  [REGION_SELECTED]                                       │
│  State: { bodyRegion: "eye_ear", categories: [],        │
│           diseases: [glaucoma, cataracts, ...] }        │
│  View: Region highlighted, disease list shown           │
│                                                          │
│         ↓ toggleCategory(category)                      │
│                                                          │
│  [CATEGORIES_APPLIED]                                    │
│  State: { bodyRegion: "eye_ear", categories: ["cancer"], │
│           diseases: [eye_melanoma] }                    │
│  View: Filtered disease list, drug preview              │
│                                                          │
│         ↓ selectDisease(disease)                        │
│                                                          │
│  [DISEASE_SELECTED]                                      │
│  State: { bodyRegion: "eye_ear", categories: ["cancer"], │
│           selectedDisease: "eye_melanoma",              │
│           drugs: [tebentafusp, ...] }                   │
│  View: Disease detail, full drug list                   │
│                                                          │
│         ↓ clearFilters()                                │
│                                                          │
│  [DEFAULT]                                               │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### State Object

```javascript
{
  // Body region filter (single select)
  bodyRegion: null | "eye_ear" | "lung_respiratory" | ...,
  
  // Disease category filters (multi-select, AND logic)
  categories: ["cancer"] | ["orphan"] | ["cancer", "orphan"] | [],
  
  // Selected disease (single select)
  selectedDisease: null | "eye_melanoma" | ...,
  
  // Computed from filters
  diseases: [],   // Diseases matching bodyRegion + categories
  drugs: []       // Drugs for selected disease (or all diseases if none selected)
}
```

---

## Frontend Implementation Guide

### Component Hierarchy

```
<App>
  <BodyMap onRegionSelect={setBodyRegion} />
  <DiseaseFilters 
    categories={categories} 
    onToggle={toggleCategory} 
  />
  <DiseaseList 
    diseases={filteredDiseases} 
    onSelect={selectDisease} 
  />
  <DrugList 
    drugs={drugs} 
    orphanIndicators={true} 
  />
</App>
```

### Event Handlers

```javascript
// Select body region
function selectBodyRegion(region) {
  setState(prev => ({
    ...prev,
    bodyRegion: region,
    selectedDisease: null,
    diseases: getDiseasesByRegion(region),
    drugs: []
  }));
}

// Toggle category filter
function toggleCategory(category) {
  setState(prev => {
    const categories = prev.categories.includes(category)
      ? prev.categories.filter(c => c !== category)
      : [...prev.categories, category];
    
    const diseases = applyCategoryFilters(
      getDiseasesByRegion(prev.bodyRegion),
      categories
    );
    
    return {
      ...prev,
      categories,
      diseases,
      selectedDisease: null,
      drugs: []
    };
  });
}

// Select disease
function selectDisease(disease) {
  setState(prev => ({
    ...prev,
    selectedDisease: disease,
    drugs: getDrugsForDisease(disease.id)
  }));
}
```

---

## Prevalence Tiers

Diseases are categorized by prevalence for filtering:

| Tier | Prevalence | Examples |
|------|------------|----------|
| **Common** | >1M patients | Hypertension, T2DM, Asthma, COPD |
| **Uncommon** | 100K-1M patients | NSCLC, Breast Cancer, Lymphoma |
| **Rare (Orphan)** | <100K patients | CML, Crohn's, Eye Melanoma, SLE |

### Orphan Thresholds

- **USA**: <200,000 people
- **Europe**: <1 in 2,000 people (~250,000 in EU)
- **Japan**: <50,000 people

---

## Search and Autocomplete

### Search Scopes

1. **Disease Search**: Search diseases by name, synonyms
2. **Drug Search**: Search drugs by name, targets, class
3. **Combined Search**: Search both, show categorized results

### Search Result Prioritization

```javascript
function searchDrugs(query, filters) {
  const results = [];
  
  // 1. Exact name matches (highest priority)
  results.push(...exactMatch(query, 'name'));
  
  // 2. Synonym matches
  results.push(...partialMatch(query, 'synonyms'));
  
  // 3. Target matches
  results.push(...partialMatch(query, 'targets'));
  
  // 4. Disease matches (show drugs for matched diseases)
  const diseaseMatches = searchDiseases(query);
  results.push(...getDrugsForDiseases(diseaseMatches));
  
  // Apply current filters
  return applyFilters(results, filters);
}
```

---

## Performance Considerations

### Lazy Loading

- Diseases loaded per region (not all at once)
- Drugs loaded per disease (on selection)
- Structure rendering deferred until modal open

### Caching Strategy

```javascript
const cache = {
  bodyRegions: {},      // { "eye_ear": {...} }
  diseases: {},         // { "eye_ear": [glaucoma, ...] }
  drugs: {},            // { "glaucoma": [latanoprost, ...] }
  structures: {}        // { "latanoprost": "<svg>..." }
};
```

---

## Current Disease Database

### Diseases by Body Region (29 total)

| Body Region | Diseases |
|-------------|----------|
| **brain_cns** | Glioma, Alzheimer's Disease, Epilepsy |
| **eye_ear** | Glaucoma, Uveal Melanoma, Retinoblastoma, Conjunctivitis, Diabetic Retinopathy |
| **lung_respiratory** | Asthma, COPD, NSCLC |
| **heart_vascular** | Hypertension, Hyperlipidemia |
| **blood_immune** | CML, Lymphoma |
| **stomach_upper_gi** | GERD, Peptic Ulcer Disease |
| **intestine_colorectal** | Crohn's Disease, Ulcerative Colitis |
| **liver_biliary_pancreas** | Hepatocellular Carcinoma |
| **endocrine_metabolic** | Type 2 Diabetes, Hypothyroidism |
| **kidney_urinary** | Chronic Kidney Disease |
| **reproductive_breast** | BPH, Breast Cancer |
| **bone_joint_muscle** | Osteoarthritis, Osteoporosis |
| **skin** | Psoriasis |
| **systemic_multiorgan** | Systemic Lupus Erythematosus |

### Diseases by Category

#### Cancer Diseases (7)
| Disease | Body Region | Orphan? |
|---------|-------------|----------|
| Glioma | brain_cns | No |
| NSCLC | lung_respiratory | No |
| CML | blood_immune | **Yes** |
| Lymphoma | blood_immune | No |
| Hepatocellular Carcinoma | liver_biliary_pancreas | No |
| Breast Cancer | reproductive_breast | No |
| Uveal Melanoma | eye_ear | **Yes** |
| Retinoblastoma | eye_ear | **Yes** |

#### Orphan Diseases (5)
| Disease | Body Region | Categories |
|---------|-------------|------------|
| CML | blood_immune | cancer, orphan, hematologic |
| Crohn's Disease | intestine_colorectal | autoimmune, orphan, chronic |
| Ulcerative Colitis | intestine_colorectal | autoimmune, orphan, chronic |
| Systemic Lupus Erythematosus | systemic_multiorgan | autoimmune, orphan, systemic |
| Uveal Melanoma | eye_ear | cancer, orphan, sensory |
| Retinoblastoma | eye_ear | cancer, orphan, pediatric, sensory |

#### Eye + Cancer Filter Results (2 diseases)
When user selects **Eye** body region + **Cancer** category:

| Disease | Categories | Orphan? | Drugs |
|---------|------------|---------|-------|
| Uveal Melanoma | cancer, orphan, sensory | Yes | Imatinib, Pembrolizumab |
| Retinoblastoma | cancer, orphan, pediatric, sensory | Yes | Cisplatin, Etoposide, Carboplatin |

---

## Testing Checklist

### Multi-Filter Tests

- [ ] Select body region → shows correct diseases
- [ ] Add category filter → diseases filtered with AND logic
- [ ] Add second category → diseases filtered with both categories
- [ ] Remove category → diseases update correctly
- [ ] Clear all → returns to default state

### Orphan Tests

- [ ] Orphan diseases show badge in list
- [ ] Orphan drugs show indicator in card
- [ ] Orphan filter works correctly
- [ ] Orphan disease → drug relationship displayed
- [ ] Prevalence counts displayed correctly

### Navigation Tests

- [ ] Body region → disease → drug flow works
- [ ] Back navigation preserves state
- [ ] Direct URL navigation works
- [ ] Search returns to filtered state
- [ ] Clear filters resets to default

---

## File Locations

```
src/frontend/data/
├── diseases.json          # Disease database (25 diseases)
├── body-ontology.json     # Body regions (14 regions)
├── drugs-full.json        # Drug database (61+ drugs)
├── disease-to-drugs.json  # Disease → Drug mappings
└── orphan-database.json   # Orphan drug/disease registry

src/frontend/js/
├── disease-navigator.js   # Navigation state machine
├── disease-filters.js     # Filter components
└── disease-list.js        # Disease list component

database/
├── diseases/              # Comprehensive disease data
├── mappings/              # Disease-Drug mappings
└── ontology/              # Body region ontology
```

---

## Completed Tasks

- [x] **Enhance diseases.json** with category tags for all diseases (29 diseases with categories)
- [x] **Add eye-related cancer diseases** (Uveal Melanoma, Retinoblastoma, Conjunctivitis, Diabetic Retinopathy)
- [x] **Create disease-to-drugs.json** mapping file (`database/mappings/disease-to-drugs.json`)
- [x] **Add orphan status** to relevant diseases (CML, Crohn's, UC, SLE, Uveal Melanoma, Retinoblastoma)
- [x] **Fix JSON syntax errors** in anti_infective_drugs.json

## Remaining Tasks

1. **Implement frontend navigation** components for disease-first flow
2. **Add URL routing** for shareable filter states
3. **Test multi-filter** edge cases in browser
4. **Expand drug-disease mappings** to cover all 29 diseases

---

## References

- [WHO ATC/DDD Index](https://atcddd.fhi.no/)
- [FDA Orphan Drug Designation](https://www.fda.gov/industry/medical-products-orphan-drug-designation)
- [EMA Orphan Medicinal Products](https://www.ema.europa.eu/en/human-regulatory/research-development/orphan-designation)
- [NIH Genetic and Rare Diseases](https://rarediseases.info.nih.gov/)
- [Orphanet](https://www.orpha.net/)

---

*Document Version: 1.1.0*
*Created: 2026-03-14*
*Last Updated: 2026-03-14*
*Author: DrugTree Team*
