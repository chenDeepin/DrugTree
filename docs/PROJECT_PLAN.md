# DrugTree - Project Plan v0.1

> **Vision**: A visual universe of all drugs and clinical candidates, organized by therapeutic area on a human body map. Developer-friendly, no login walls, instant structure viewing.

---

## 🎯 Core Problems We're Solving

| Problem | Current State | DrugTree Solution |
|---------|---------------|-------------------|
| Structure viewing | Databases require login, captchas, slow | One-click 2D/3D viewer |
| Drug relationships | Scattered across papers, hard to trace | Visual genealogy (generation → generation) |
| Therapeutic mapping | Text-based lists, hard to visualize | Human body map with organ systems |
| Developer access | APIs limited, paywalls | Open JSON/REST, no auth for basic use |
| Data freshness | Static databases, outdated | Periodic sync from open sources |

---

## 🗺️ Visualization Architecture

### Primary View: Human Body Map
```
┌─────────────────────────────────────────────────────┐
│  [Filter Panel]  [Search Bar]  [Settings]           │
├─────────────────────────────────────────────────────┤
│                                                     │
│         ┌─────────────────────┐                    │
│         │   🧠 NEUROLOGY      │ ← Click organ      │
│         │   847 drugs         │   → Drug list      │
│         │   • Alzheimer's     │                    │
│         │   • Parkinson's     │                    │
│         └─────────────────────┘                    │
│              │          │                          │
│     ┌────────┴──┐   ┌───┴────────┐                │
│     │ ❤️ CARDIO  │   │ 🫁 RESP    │                │
│     │ 1,247     │   │ 632        │                │
│     └───────────┘   └────────────┘                │
│                                                     │
│  [Drug List Panel - Right Side]                    │
│  ┌─────────────────────────────┐                   │
│  │ Structure | Name | Phase    │                   │
│  │ ┌───┐    │ Donepezil │ IV   │                   │
│  │ │   │    │           │      │                   │
│  │ └───┘    │ Rivastigmine│ IV │                   │
│  └─────────────────────────────┘                   │
└─────────────────────────────────────────────────────┘
```

### Secondary View: Drug Genealogy Tree
```
           First Gen          Second Gen         Third Gen
              │                   │                  │
         ┌────┴────┐         ┌────┴────┐        ┌───┴───┐
         │ Imatinib│────────▶│ Dasatinib│──────▶│ Ponatinib
         │  (2001) │         │  (2006)  │        │ (2012)
         └─────────┘         └──────────┘        └────────
              │                    │
              └──────▶ Nilotinib (2007)
```

### Interaction Modes
1. **Explore** - Click body region → see all drugs for that area
2. **Search** - Type drug name → highlight on map
3. **Trace** - Click drug → show generation tree
4. **Compare** - Select 2+ drugs → side-by-side structures + properties
5. **Filter** - By phase (I/II/III/IV), by mechanism, by company

---

## 📊 Data Sources (Open Access)

### Primary Sources
| Source | Content | Access | License |
|--------|---------|--------|---------|
| **ChEMBL** | Bioactive molecules, clinical data | REST API | CC BY-SA 3.0 |
| **DrugBank** (open subset) | Approved drugs | XML dump | CC BY-NC 4.0 |
| **PubChem** | Structures, properties | REST API | Public Domain |
| **ClinicalTrials.gov** | Trial phases, indications | API | Public Domain |
| **WHO ATC** | Therapeutic classification | Downloads | CC BY 3.0 |

### Data Schema (Draft)
```json
{
  "drug_id": "CHEMBL1234",
  "name": "Imatinib",
  "smiles": "CC1=C(C=CC...",
  "inchikey": "KTUFNOKKBG...K",
  "phase": "IV",
  "atc_codes": ["L01XE01"],
  "therapeutic_area": "Oncology",
  "target_organs": ["bone_marrow", "blood"],
  "targets": ["BCR-ABL", "KIT", "PDGFR"],
  "first_approval": 2001,
  "generation": 1,
  "parent_drugs": [],
  "derived_drugs": ["CHEMBL1862", "CHEMBL554"],
  "companies": ["Novartis"],
  "molecular_weight": 493.6,
  "clinical_trials": ["NCT0001234", ...]
}
```

---

## 🏗️ Technical Architecture

### Frontend (Browser)
```
src/frontend/
├── index.html
├── css/
│   ├── main.css
│   └── human-body.css
├── js/
│   ├── app.js           # Main application
│   ├── body-map.js      # Human body SVG interactions
│   ├── structure-viewer.js  # 2D/3D molecule viewer
│   ├── genealogy.js     # Drug generation tree
│   └── search.js        # Search & filter logic
└── assets/
    ├── human-body.svg   # Interactive body map
    └── icons/
```

**Tech Choices**:
- **Structure Viewer**: `3Dmol.js` or `Kekule.js` (both open source)
- **Visual Effects**: D3.js for animations, WebGL for 3D
- **Body Map**: SVG with clickable regions

### Backend (API)
```
src/backend/
├── main.py              # FastAPI entry point
├── routers/
│   ├── drugs.py         # Drug search/details
│   ├── structures.py    # Molecule rendering
│   └── relationships.py # Genealogy queries
├── models/
│   └── drug.py          # Pydantic models
└── database/
    └── drugs.json       # Static JSON (v1)
```

**Tech Choices**:
- **Framework**: FastAPI (Python, async, auto-docs)
- **Data**: Start with JSON files, migrate to SQLite/PostgreSQL later
- **No Auth**: Open access, rate limiting only

### ETL Pipeline
```
src/etl/
├── fetch_chembl.py      # ChEMBL API sync
├── fetch_drugbank.py    # DrugBank open subset
├── fetch_pubchem.py     # Structure data
├── fetch_clinical.py    # ClinicalTrials.gov
├── build_index.py       # Create search indices
└── normalize.py         # Dedupe, merge records
```

**Sync Schedule**: Weekly cron job

---

## 📅 Development Phases

### Phase 1: MVP (Week 1-2)
**Goal**: Basic working prototype

- [ ] Set up project structure
- [ ] Fetch sample data from ChEMBL (100 drugs)
- [ ] Create human body SVG map
- [ ] Implement basic structure viewer (2D)
- [ ] Click organ → show drug list
- [ ] Deploy to GitHub Pages

**Deliverable**: Static site with 100 drugs, basic body map

### Phase 2: Data Pipeline (Week 3-4)
**Goal**: Automated data sync

- [ ] Build ETL scripts for all sources
- [ ] Create unified drug schema
- [ ] Build search index
- [ ] Add drug metadata (phase, company, targets)
- [ ] Expand to 1000+ drugs

**Deliverable**: Automated weekly data updates

### Phase 3: Genealogy (Week 5-6)
**Goal**: Drug relationship mapping

- [ ] Implement parent/child drug relationships
- [ ] Build generation tree visualization
- [ ] Add mechanism-based clustering
- [ ] Cross-link to clinical trials

**Deliverable**: Click drug → see evolution tree

### Phase 4: Polish (Week 7-8)
**Goal**: Production quality

- [ ] 3D structure viewer
- [ ] Advanced filtering (phase, target, company)
- [ ] Performance optimization (lazy loading)
- [ ] Mobile responsive design
- [ ] API documentation

**Deliverable**: Public launch

---

## ❓ Open Questions (Discuss!)

### 1. Therapeutic Categories
What's the right level of granularity?

**Option A**: WHO ATC Level 1 (14 categories)
- Cardiovascular, Nervous system, Anti-infectives, etc.

**Option B**: User-friendly groups (~8)
- Cancer, Infection, Pain, Heart, Brain, Diabetes, Autoimmune, Other

**My suggestion**: Start with Option B (simpler), add ATC drill-down later.

### 2. Drug Generation Definition
How do we define "generation"?

**Ideas**:
- By approval year (2000s = Gen 1, 2010s = Gen 2...)
- By structural lineage (parent drug → optimized derivative)
- By mechanism evolution (first-in-class vs best-in-class)

**My suggestion**: Structural lineage + approval year, show both.

### 3. Body Map Detail
How detailed should the human body visualization be?

**Option A**: Simplified (8-10 organ systems)
**Option B**: Anatomical (20+ organs)
**Option C**: Both (toggle between views)

**My suggestion**: Start with Option A, add Option C later.

### 4. Structure Viewer
2D vs 3D?

**2D**: Faster, cleaner, good for quick recognition
**3D**: More impressive, shows stereochemistry

**My suggestion**: 2D default, 3D on click (like O-DataMap's drill-down).

### 5. Data Priority
Which drugs to include first?

- **Approved drugs only** (~2000) → Cleaner, more complete
- **All clinical candidates** (~10000+) → More comprehensive, messier

**My suggestion**: Start with approved, add clinical candidates in Phase 2.

---

## 🚀 Quick Start Plan

Let's build a minimal prototype THIS SESSION:

1. Create human body SVG (simplified)
2. Fetch 50 sample drugs from ChEMBL
3. Build basic HTML/CSS/JS structure
4. Wire click → show drug + structure
5. Push to GitHub Pages

**Then iterate based on feedback.**

---

## 📝 Next Steps

1. **Your input needed**: Answer the 5 open questions above
2. **I'll start**: Building the MVP structure
3. **We'll refine**: Based on what you see working

---

*Created: 2026-03-13*
*Version: 0.1 (Initial Plan)*
*Status: Ready for Discussion*

---

## ✅ Design Decisions (2026-03-13)

Based on user feedback:

| Question | Decision | Notes |
|----------|----------|-------|
| 1. Therapeutic Categories | **8 simple groups** | Cancer, Infection, Pain, Heart, Brain, Diabetes, Autoimmune, Other |
| 2. Drug Generation | **Both** | Approval year + structural lineage, dual view |
| 3. Body Map Detail | **Simplified first** | 8-10 organ systems, add anatomical later |
| 4. Structure Viewer | **2D → 3D** | 2D default, click for 3D |
| 5. Data Scope | **Approved first** | ~2000 drugs, add clinical candidates in Phase 2 |

---

## 🎨 Updated MVP Scope

### Therapeutic Categories (8 Groups)
```yaml
categories:
  - id: cancer
    name: Cancer / Oncology
    icon: 🎗️
    organs: [bone_marrow, blood, lymph, tissues]
    atc_codes: [L01, L02, L03]
    
  - id: infection
    name: Infection
    icon: 🦠
    organs: [blood, lungs, skin, gut]
    atc_codes: [J01, J02, J04, J05]
    
  - id: pain
    name: Pain & Inflammation
    icon: 💊
    organs: [nerves, brain, joints]
    atc_codes: [M01, N02]
    
  - id: heart
    name: Heart & Cardiovascular
    icon: ❤️
    organs: [heart, blood_vessels, blood]
    atc_codes: [C01, C02, C03, C07, C08, C09, C10]
    
  - id: brain
    name: Brain & Neurology
    icon: 🧠
    organs: [brain, nerves, spinal_cord]
    atc_codes: [N03, N04, N05, N06, N07]
    
  - id: diabetes
    name: Diabetes & Metabolism
    icon: 🩸
    organs: [pancreas, liver, fat]
    atc_codes: [A10]
    
  - id: autoimmune
    name: Autoimmune & Immunity
    icon: 🛡️
    organs: [immune_system, joints, skin]
    atc_codes: [L04, M01, H02]
    
  - id: other
    name: Other
    icon: ⚕️
    organs: [various]
    atc_codes: [A, B, D, G, H, R, S, V]
```

### Body Map Regions (Simplified)
```
┌─────────────────────────────────┐
│        🧠 Brain/Neuro          │
├─────────────────────────────────┤
│  🫁 Lungs    ❤️ Heart          │
│            (Infection)  (Cardio)│
├─────────────────────────────────┤
│   🫄 Gut      🩸 Pancreas      │
│  (Infection)  (Diabetes)        │
├─────────────────────────────────┤
│   🦴 Bones    🦠 Immune         │
│   (Cancer)    (Autoimmune)      │
├─────────────────────────────────┤
│   🤲 Skin & Joints              │
│   (Pain, Autoimmune)            │
└─────────────────────────────────┘
```

---

*Updated: 2026-03-13 15:35*
*Version: 0.2 (Design Decisions Locked)*

---

## ✅ Interaction Decisions (2026-03-13, round 2)

Based on user feedback, DrugTree interaction logic is now defined as a **dual-filter atlas**:

### Core Interaction Principle
Users should be able to locate drugs by combining:
1. **ATC / treatment label** → what kind of therapy it is
2. **Human body position** → where the disease/treatment context sits in the body

This combination is central to the product.

### Why ATC Labels Matter
ATC labels are not just metadata; they are a **precision filter layer**.
They let the user quickly narrow the universe to the exact treatment class they want.

Examples:
- Select **Cancer / antineoplastic context** → exclude autoimmune/immunology drugs from the view
- Select **Anti-infectives** → focus on infection-related agents only
- Select **Cardiovascular** → narrow to heart/vascular drugs

### Why Human Body View Matters
The body map is the **spatial navigation layer**.
It helps users find the right drug set intuitively by disease location or treatment context.

Examples:
- Choose **Cancer** then hover/select **Brain** → surface glioma / CNS oncology drugs
- Choose **Respiratory** then hover/select **Lung** → show asthma / COPD / respiratory infection drugs
- Choose **Gastrointestinal / metabolism** then hover/select **Gut / stomach** → show GI drugs

### Planned Interaction Pattern
**Primary interaction flow:**
1. User selects an **ATC/treatment label**
2. User hovers over or selects a **body region**
3. After a short dwell time (e.g. 1-2 seconds), matching drugs are previewed
4. Clicking opens detailed cards / structure / lineage view

### UI Behavior Decision
- **ATC labels = hard filter / primary filter**
- **Body regions = spatial refinement / discovery layer**
- **Hover dwell = quick preview**
- **Click = full detail view**

### Product Identity (Locked)
DrugTree is a:
- **clinical atlas on the surface**
- **medicinal chemistry explorer underneath**

### Navigation Modes (Locked)
DrugTree will support these layers:
1. **ATC label filtering** - exact therapeutic filtering
2. **Body map exploration** - intuitive spatial discovery
3. **Drug cards** - structures + key metadata
4. **Family / lineage view** - medicinal chemistry depth
5. **Target / indication relationships** - future graph layer

### Example Golden Workflow
> User wants glioma drugs.
> 
> - Select **L / Antineoplastic and immunomodulating agents**
> - Hover over **Brain**
> - Wait briefly for preview list
> - Open a drug card
> - Inspect structure, target, family, generation

This workflow is now a canonical design target for MVP evolution.

### Implication for Data Model
Each drug record must support both:
- **official classification** (ATC)
- **visual placement** (body region / disease organ / systemic flag)

So body mapping must be stored independently from ATC.

---

## 🔜 Next Design Stage

The next stage should define three connected specifications:

1. **DrugTree schema v1**
   - drug fields
   - family fields
   - target fields
   - indication fields
   - body placement fields

2. **Body-region ontology v1**
   - brain
   - lung
   - heart/vasculature
   - blood/immune
   - gut/liver
   - endocrine/metabolism
   - skin
   - bone/joint/muscle
   - kidney/urinary/reproductive
   - eye/ear
   - systemic / multi-organ

3. **Filtering logic v1**
   - ATC only
   - body only
   - ATC + body intersection
   - hover preview rules
   - systemic drug handling

*Updated: 2026-03-13 16:26*
*Version: 0.3 (Dual-filter atlas interaction locked)*

---

## ✅ UX Decisions (2026-03-13, round 3)

Based on user approval, the following interaction decisions are now locked:

### Body Selection Behavior
- **Hover (1-2 seconds)** = quick preview
- **Click** = lock selected body region
- This supports both fast exploration and deliberate selection

### Systemic Drug Placement
Systemic drugs should use:
- **primary organ placement** when relevant
- plus a **systemic tag**

This avoids hiding systemic agents while still anchoring them to a useful clinical context.

### Drug Card Preview Content
The default visible layer after filtering should show:
- **drug name**
- **structure thumbnail**
- **ATC mini-tag**

This gives enough chemistry + classification context without needing a click first.

### Oncology Placement Rule
For oncology and similar disease-driven areas, body placement should follow:
- **disease location first**
- **pharmacology class as metadata**

Example:
- Glioma drug → place under **brain**
- ATC and target class remain visible in metadata/filter layers

### Locked Product Behavior Summary
DrugTree interaction now follows this model:
1. Select **ATC/treatment label**
2. Hover over **body region** for preview
3. Click body region to lock selection
4. Review **drug cards** with structure + ATC tag
5. Open detail for chemistry, targets, lineage, evidence

---

## 🔜 Next Stage Definition

The next stage is to define and freeze **DrugTree Schema v1**.

This schema should cover at minimum:
- `drug`
- `family`
- `target`
- `indication`
- `body_placement`

### Schema Goal
Create a data model that supports all future views:
- ATC filtering
- body-map navigation
- chemistry-rich drug cards
- lineage/family exploration
- future target/disease graph relationships

*Updated: 2026-03-13 16:28*
*Version: 0.4 (UX behavior locked; schema v1 next)*

---

## ✅ Schema Direction Decisions (2026-03-13, round 4)

Based on user approval, DrugTree Schema v1 will follow these principles:

### Family Definition Priority
Drug relationships should be organized with:
1. **Primary family = scaffold / lineage family**
2. **Secondary family = target-class family**
3. **Additional relationship layers = indication / company / mechanism**

This ensures DrugTree remains useful for medicinal chemistry reasoning while still supporting pharmacology views.

### Indication Hierarchy
Clinical organization should follow:
1. **Organ system**
2. **Disease area**
3. **Specific indication**

Example:
- Brain/CNS → Oncology → Glioma
- Lung/Respiratory → Infection → Community-acquired pneumonia
- Gut/Liver → Metabolism → Type 2 diabetes

### Body Placement Authority Rules
If body-region mapping conflicts, priority should be:
1. **Disease location**
2. **Clinical use system**
3. **Pharmacology system**
4. **Administration site**

This rule should govern all future placement decisions.

### Schema Strategy
DrugTree should use:
- **drug-first records** as the canonical storage model
- **family-first navigation** as the exploratory chemistry layer

This preserves clean records while enabling lineage, scaffold, and target exploration.

### Canonical Schema Scope (v1)
Schema v1 must support:
- official ATC classification
- human-body placement
- medicinal chemistry descriptors
- target relationships
- family/lineage relationships
- evidence/source provenance
- future bilingual expansion

### Example Records for Validation
Schema v1 should be validated using representative examples from different contexts:
- **Imatinib** - oncology, targeted therapy, lineage-rich
- **Osimertinib** - later-generation targeted oncology drug
- **Omeprazole** - GI/alimentary classic small molecule
- **Metformin** - metabolism / systemic drug
- **Sertraline** - CNS indication with nervous-system placement

---

## 🔜 Next Stage Definition (Active)

The next active planning stage is:

### DrugTree Schema v1 Draft
Create a formal schema for:
- `drug`
- `family`
- `target`
- `indication`
- `body_placement`
- optional `evidence_source`

### Deliverable Goal
Produce:
1. a canonical field specification
2. relationship rules between entities
3. 3-5 example records using real drugs
4. notes on what is mandatory vs optional in early MVP

*Updated: 2026-03-13 16:32*
*Version: 0.5 (schema direction locked; schema draft next)*

---

## ✅ Audience Mode Decision (2026-03-13, round 5)

Based on user feedback, DrugTree should support **two audience modes** via a page-level switch.

### Why This Matters
Different users need different levels of detail:
- **General / non-specialist users** care mainly about drug names, what diseases they treat, and where in the body they are relevant.
- **Scientists / industry / academic users** want chemistry-heavy and mechanism-rich details.

### Locked UX Decision
Add a top-level mode switch:
- **Public Mode** (or Simple Mode)
- **Scientist Mode** (or Expert Mode)

### Mode Behavior

#### 1. Public Mode
Focus on accessibility and clinical meaning.

Show by default:
- drug name
- brand/common synonyms
- treatment / indication
- ATC label
- body location relevance
- brief mechanism summary
- approval status / year
- simple description

Hide or collapse by default:
- SMILES
- InChIKey
- TPSA
- cLogP
- HBA/HBD
- scaffold details
- detailed lineage graph
- target technical notes

#### 2. Scientist Mode
Focus on medicinal chemistry and technical exploration.

Show by default:
- 2D structure
- SMILES / InChIKey
- MW, cLogP, TPSA, HBA/HBD, rotatable bonds
- scaffold/core family
- target(s)
- mechanism details
- lineage/generation links
- source provenance

### Product Framing
DrugTree should feel like:
- **an intuitive treatment atlas in Public Mode**
- **a medicinal chemistry explorer in Scientist Mode**

### Data Model Implication
The schema should remain rich, but the UI should expose fields conditionally by mode.

This means:
- **one canonical data schema**
- **multiple presentation layers**

### UI Placement Suggestion
Top-right page switch:
- `Public` | `Scientist`

Optional future variants:
- Public
- Clinician
- Scientist

But MVP should start with **two modes only**.

### Default Mode Recommendation
Default to **Public Mode**, with Scientist Mode one click away.

Reason:
- safer for general usability
- cleaner first impression
- still preserves expert depth when needed

---

## 🔜 Next Schema Requirement
Schema v1 must mark fields by display tier:
- `public_core`
- `expert_core`
- `advanced_expert`

This will help drive the mode switch cleanly in the frontend.

*Updated: 2026-03-13 16:39*
*Version: 0.6 (audience-mode switch locked)*

---

## ✅ Audience Mode UX Details (2026-03-13, round 6)

Based on user approval, the audience-mode system is now further specified.

### Mode Names (Locked)
Use:
- **Public**
- **Scientist**

These labels are clear, intuitive, and fit the product identity.

### Public Mode Structure Visibility
Public Mode should show:
- **small structure thumbnail only**

Reason:
- keeps visual identity of molecules present
- avoids overwhelming non-specialists with technical chemistry details
- still helps users recognize that drugs are distinct molecules

### Scientist Mode Default Detail Level
Scientist Mode should open with:
- **compact expert card by default**
- expandable to full chemistry detail

Reason:
- preserves scanability when browsing many drugs
- avoids dumping too much information at once
- supports fast exploration plus deep dive on demand

### Presentation Rule Summary
- **Public Mode** = simple card, treatment-focused, small structure thumbnail
- **Scientist Mode** = compact expert card, expandable to full chem/target/lineage detail

### Product Principle
DrugTree should never require separate datasets for different audiences.
Instead:
- one canonical record
- multiple display modes
- progressive disclosure of complexity

---

## 🔜 Next Active Stage

Next stage: **DrugTree Schema v1 Draft with display tiers**

The schema draft must now explicitly support:
- `public_core`
- `expert_core`
- `advanced_expert`

And it should define field groups for:
- identity
- classification
- clinical use
- chemistry
- biology
- lineage
- body placement
- evidence/source provenance

*Updated: 2026-03-13 16:41*
*Version: 0.7 (mode UX details locked; schema draft active)*

---

## ✅ Anatomical Ontology Direction (2026-03-13, round 7)

Based on user approval, DrugTree will adopt a **detailed anatomical ontology from the start**.

### Core Modeling Principle
DrugTree should use two connected layers:
1. **Detailed anatomical ontology layer** for data/modeling
2. **Simplified visual body-map layer** for initial user interaction

This allows the data model to remain precise while the UI stays intuitive.

### Ontology Strategy (Locked)
- **Detailed ontology in schema from day one**
- **Simplified visible body map in early UI**
- **Progressive drill-down later** for finer anatomy and disease-specific navigation

### Major Visible UI Regions (v1 recommendation adopted)
The early UI should expose roughly these major regions:
- brain_cns
- eye_ear
- lung_respiratory
- heart_vascular
- blood_immune
- stomach_upper_gi
- intestine_colorectal
- liver_biliary_pancreas
- endocrine_metabolic
- kidney_urinary
- reproductive_breast
- bone_joint_muscle
- skin
- systemic_multiorgan

### Internal Ontology Granularity
The schema should support deeper internal nodes under each major region.
Examples:
- brain -> cerebrum / glioma-related nodes / meninges / pituitary context
- lung -> airway / parenchyma / NSCLC / SCLC context
- blood_immune -> blood / bone_marrow / spleen / lymphatic_system
- gi -> stomach / small_intestine / colon_rectum
- hepatobiliary_pancreatic -> liver / gallbladder_bile_duct / pancreas
- reproductive_breast -> breast / prostate / ovary / uterus_cervix / testis

### Modeling Rule: Anatomy vs Disease
Anatomy and disease must remain separate concepts.
DrugTree should model:
- **anatomy nodes**
- **disease nodes**
- **drug records**

With mappings such as:
- disease -> anatomy
- drug -> disease
- drug -> body placement

### Drug Placement Fields (Locked)
Drug placement should distinguish:
- `primary_disease_site`
- `secondary_disease_sites`
- `pharmacology_system`
- `administration_site`
- `systemic_flag`

This avoids forcing one misleading placement for systemic drugs.

### Additional Ontology Decisions (Locked)
- **Breast** should be treated as its own important context within `reproductive_breast` and may become its own visible region later if oncology needs demand it.
- **Liver and pancreas** may be grouped visually at first, but remain separate ontology nodes.
- **Hematologic malignancies** should be visually anchored in `blood_immune`, while `bone_marrow` remains an internal ontology node.
- **GI should be split visually** into at least `stomach_upper_gi` and `intestine_colorectal` in the first meaningful UI iteration.

### Product Principle Reinforced
DrugTree is not a purely anatomical browser.
It is a connected system spanning:
- anatomy
- disease
- pharmacology
- chemistry
- lineage

The anatomical ontology is one axis, not the whole model.

---

## 🔜 Next Active Stage

Next stage: **Body Ontology v1 draft**

This should define:
1. visible body-map regions
2. internal anatomical nodes
3. disease-to-anatomy mappings
4. placement rules for systemic vs localized drugs
5. examples for oncology, infection, GI, CNS, and immune diseases

*Updated: 2026-03-13 16:50*
*Version: 0.8 (detailed anatomical ontology direction locked; body ontology draft next)*

---

## 🧩 Consolidated Design Modules (kept inside this plan file)

Instead of creating separate design docs, DrugTree will keep four short implementation-guiding modules directly inside `PROJECT_PLAN.md`:

1. **Schema v1**
2. **Body Ontology v1**
3. **Curation Rules v1**
4. **Interaction Spec v1**

These modules should stay concise, implementation-oriented, and versioned in this file.

---

# Module 1 — DrugTree Schema v1

## 1. Purpose
Schema v1 defines the canonical record structure for DrugTree.
It must support:
- ATC filtering
- body-map navigation
- Public / Scientist display modes
- medicinal chemistry exploration
- lineage/family relationships
- source provenance

**Canonical strategy:**
- **drug-first storage**
- **family-first exploration**
- **nested schema**
- **single rich record, multiple display modes**

---

## 2. Entity Scope (v1)
Schema v1 should support these conceptual entities:
- `drug`
- `family`
- `target`
- `indication`
- `body_placement`
- `evidence_source` (lightweight in v1)

For MVP implementation, the main working object is still the **drug record**, with embedded references to the others.

---

## 3. Drug Record Structure (Nested)

```yaml
drug:
  identity:
    drug_id: string
    name_en: string
    name_zh: string | null
    synonyms: [string]
    brand_names: [string]

  classification:
    atc_code: string
    atc_level1: string
    atc_level1_label: string
    drug_class: string
    public_core_labels: [string]

  clinical:
    organ_system: string
    disease_area: string
    specific_indications: [string]
    treatment_summary_public: string
    indication_notes_expert: string | null

  body_placement:
    primary_disease_site: string
    secondary_disease_sites: [string]
    pharmacology_system: string
    administration_site: string | null
    systemic_flag: boolean
    placement_basis: string

  chemistry:
    smiles: string
    inchikey: string
    molecular_weight: number
    clogp: number | null
    tpsa: number | null
    hba: integer | null
    hbd: integer | null
    rotatable_bonds: integer | null
    ring_count: integer | null
    aromatic_ring_count: integer | null
    stereocenter_count: integer | null
    scaffold_core: string | null

  biology:
    targets: [string]
    mechanism: string
    pathway: string | null
    target_notes_zh: string | null

  lineage:
    lineage_family_id: string | null
    scaffold_family_id: string | null
    target_family_id: string | null
    generation: string | integer | null
    parent_drugs: [string]
    successor_drugs: [string]
    lineage_notes: string | null

  development:
    approval_year: integer | null
    max_phase: string
    company: [string]
    approval_regions: [string]

  evidence:
    pubchem_id: string | null
    chembl_id: string | null
    drugbank_id: string | null
    clinicaltrials_refs: [string]
    sources: [object]

  display_tiers:
    public_core: [string]
    expert_core: [string]
    advanced_expert: [string]
```

---

## 4. Required vs Optional Fields

### Required for MVP
These should exist for every v1 drug record:

```yaml
required_mvp_fields:
  - identity.drug_id
  - identity.name_en
  - classification.atc_code
  - classification.atc_level1
  - classification.atc_level1_label
  - classification.drug_class
  - clinical.organ_system
  - clinical.disease_area
  - clinical.specific_indications
  - clinical.treatment_summary_public
  - body_placement.primary_disease_site
  - body_placement.systemic_flag
  - body_placement.placement_basis
  - chemistry.smiles
  - chemistry.inchikey
  - chemistry.molecular_weight
  - biology.targets
  - biology.mechanism
  - development.approval_year
  - development.max_phase
  - development.company
  - evidence.sources
```

### Recommended soon after MVP
```yaml
recommended_v1_1:
  - identity.name_zh
  - identity.brand_names
  - chemistry.clogp
  - chemistry.tpsa
  - chemistry.hba
  - chemistry.hbd
  - chemistry.rotatable_bonds
  - chemistry.scaffold_core
  - lineage.lineage_family_id
  - lineage.scaffold_family_id
  - lineage.target_family_id
  - lineage.generation
  - development.approval_regions
  - evidence.pubchem_id
  - evidence.chembl_id
```

### Advanced / later-stage
```yaml
advanced_future:
  - chemistry.stereocenter_count
  - chemistry.aromatic_ring_count
  - biology.pathway
  - biology.target_notes_zh
  - lineage.parent_drugs
  - lineage.successor_drugs
  - lineage.lineage_notes
  - evidence.clinicaltrials_refs
  - per-field provenance confidence
```

---

## 5. Display Tier Rules

### Public Mode
Public Mode should primarily expose these fields:
- `identity.name_en`
- `identity.name_zh` (when available)
- `identity.brand_names`
- `classification.atc_level1_label`
- `classification.drug_class`
- `clinical.treatment_summary_public`
- `clinical.specific_indications`
- `body_placement.primary_disease_site`
- `development.approval_year`
- small 2D structure thumbnail

### Scientist Mode
Scientist Mode should expose Public Mode plus:
- `chemistry.smiles`
- `chemistry.inchikey`
- `chemistry.molecular_weight`
- `chemistry.clogp`
- `chemistry.tpsa`
- `chemistry.hba`
- `chemistry.hbd`
- `chemistry.rotatable_bonds`
- `chemistry.scaffold_core`
- `biology.targets`
- `biology.mechanism`
- `lineage.*`
- `evidence.sources`

### Advanced Expert Expansion
Can additionally show:
- parent/successor lineage graph
- provenance details
- source IDs
- future SAR / similarity fields

---

## 6. Family ID Strategy
DrugTree should support multiple family axes.

```yaml
family_axes:
  scaffold_family_id: chemistry-derived family
  target_family_id: biology/target-derived family
  lineage_family_id: medicinal-chemistry or historical evolution family
```

### Rule
- **Primary exploration family** = `lineage_family_id` or `scaffold_family_id`
- **Secondary exploration family** = `target_family_id`

This keeps DrugTree useful both as a chemistry explorer and as a pharmacology browser.

---

## 7. Placement Authority Rules
When placement conflicts exist, resolve using:
1. **disease location**
2. **clinical use system**
3. **pharmacology system**
4. **administration site**

### Examples
- Glioma drug → `brain_cns`
- CML drug → `blood_immune` with internal `bone_marrow` mapping
- Omeprazole → `stomach_upper_gi`
- Prednisone → systemic with disease-context-specific placement where needed

---

## 8. Lightweight Evidence Source Object (v1)

```yaml
evidence_source:
  source_name: string        # PubChem / ChEMBL / DrugBank / curated
  source_url: string | null
  source_id: string | null
  field_scope: [string]      # e.g. ["smiles", "inchikey"]
  note: string | null
```

This is intentionally lightweight for MVP.

---

## 9. Example Minimal Record Shape

```json
{
  "identity": {
    "drug_id": "drug_imatinib",
    "name_en": "Imatinib",
    "name_zh": null,
    "synonyms": ["STI-571"],
    "brand_names": ["Gleevec", "Glivec"]
  },
  "classification": {
    "atc_code": "L01XE01",
    "atc_level1": "L",
    "atc_level1_label": "Antineoplastic and immunomodulating agents",
    "drug_class": "BCR-ABL tyrosine kinase inhibitor",
    "public_core_labels": ["Cancer", "Targeted therapy"]
  },
  "clinical": {
    "organ_system": "hematologic_immune",
    "disease_area": "Oncology",
    "specific_indications": ["Chronic myeloid leukemia", "GIST"],
    "treatment_summary_public": "A targeted anti-cancer drug used mainly for leukemia and certain solid tumors.",
    "indication_notes_expert": null
  },
  "body_placement": {
    "primary_disease_site": "blood_immune",
    "secondary_disease_sites": ["gastrointestinal"],
    "pharmacology_system": "systemic_antineoplastic",
    "administration_site": "oral",
    "systemic_flag": true,
    "placement_basis": "disease_location"
  },
  "chemistry": {
    "smiles": "CC1=C(C=CC=C1)NC(=O)C2=CC(=C(C=C2)NCC3=CN=CC=C3)C",
    "inchikey": "KTUFNOKKBVMGRW-UHFFFAOYSA-N",
    "molecular_weight": 493.6,
    "clogp": null,
    "tpsa": null,
    "hba": null,
    "hbd": null,
    "rotatable_bonds": null,
    "ring_count": null,
    "aromatic_ring_count": null,
    "stereocenter_count": null,
    "scaffold_core": null
  },
  "biology": {
    "targets": ["BCR-ABL", "KIT", "PDGFR"],
    "mechanism": "Tyrosine kinase inhibition",
    "pathway": null,
    "target_notes_zh": null
  },
  "lineage": {
    "lineage_family_id": "fam_bcr_abl_tki",
    "scaffold_family_id": null,
    "target_family_id": "targetfam_abl_kit_tki",
    "generation": 1,
    "parent_drugs": [],
    "successor_drugs": ["Dasatinib", "Nilotinib", "Ponatinib"],
    "lineage_notes": null
  },
  "development": {
    "approval_year": 2001,
    "max_phase": "IV",
    "company": ["Novartis"],
    "approval_regions": []
  },
  "evidence": {
    "pubchem_id": null,
    "chembl_id": null,
    "drugbank_id": null,
    "clinicaltrials_refs": [],
    "sources": []
  }
}
```

---

## 10. Implementation Notes
- Start with JSON records matching this nested shape.
- Flatten only in frontend view models if necessary.
- Do not create separate Public vs Scientist datasets.
- Missing chemistry descriptors are acceptable in MVP if structure identity is present.
- Family IDs may be null until lineage curation is mature.

---

## 11. Open Follow-up for Module 2
Schema v1 now depends on a stable `body_placement.primary_disease_site` vocabulary.
That vocabulary will be defined in **Module 2 — Body Ontology v1**.

*Updated: 2026-03-13 16:58*
*Version: 0.9 (Schema v1 drafted inside master plan)*

---

# Module 2 — Body Ontology v1

## 1. Purpose
Body Ontology v1 defines how DrugTree maps drugs and diseases onto the human body.
It must support:
- intuitive visual navigation
- precise anatomical modeling
- disease-location-based placement
- systemic drug handling
- future drill-down from major regions to finer anatomy

### Core Principle
DrugTree uses **two connected layers**:
1. **Visible UI body regions** for user interaction
2. **Internal anatomical ontology nodes** for precise data modeling

This allows the interface to stay elegant while the data remains rich.

---

## 2. Top-Level Visible UI Regions (v1)
These are the regions users can directly hover/click on the body map in the first meaningful implementation.

| region_id | display_name | visible_in_ui | Notes |
|---|---|---:|---|
| `brain_cns` | Brain / CNS | yes | CNS diseases, neuro, brain tumors |
| `eye_ear` | Eye / Ear | yes | sensory-organ drugs |
| `lung_respiratory` | Lung / Respiratory | yes | asthma, COPD, respiratory infection, lung cancer |
| `heart_vascular` | Heart / Vascular | yes | cardiovascular disease, hypertension, lipids |
| `blood_immune` | Blood / Immune | yes | leukemia, lymphoma, immune disorders, hematology |
| `stomach_upper_gi` | Stomach / Upper GI | yes | reflux, ulcer, upper GI disease |
| `intestine_colorectal` | Intestine / Colorectal | yes | IBD, colorectal disease, lower GI infections |
| `liver_biliary_pancreas` | Liver / Biliary / Pancreas | yes | liver disease, biliary disease, pancreas context |
| `endocrine_metabolic` | Endocrine / Metabolic | yes | diabetes, thyroid, metabolic disease |
| `kidney_urinary` | Kidney / Urinary | yes | renal and urinary conditions |
| `reproductive_breast` | Reproductive / Breast | yes | breast, ovarian, uterine, prostate, fertility |
| `bone_joint_muscle` | Bone / Joint / Muscle | yes | arthritis, bone disease, musculoskeletal pain |
| `skin` | Skin | yes | dermatology, inflammatory skin disease |
| `systemic_multiorgan` | Systemic / Multi-organ | yes | whole-body/systemic diseases and agents |

### Design Decision
Visible UI stays at roughly **14 regions**, which balances clarity and usefulness.

---

## 3. Internal Anatomical Ontology Nodes (v1)
These are finer-grained nodes stored in data, even if not all are directly visible in the early UI.

### 3.1 CNS
| node_id | parent_region | display_name |
|---|---|---|
| `brain` | `brain_cns` | Brain |
| `cerebrum` | `brain` | Cerebrum |
| `brainstem` | `brain` | Brainstem |
| `cerebellum` | `brain` | Cerebellum |
| `spinal_cord` | `brain_cns` | Spinal cord |
| `peripheral_nervous_system` | `brain_cns` | Peripheral nervous system |
| `meninges` | `brain_cns` | Meninges |
| `pituitary_region` | `brain_cns` | Pituitary region |

### 3.2 Sensory Organs
| node_id | parent_region | display_name |
|---|---|---|
| `eye` | `eye_ear` | Eye |
| `retina` | `eye` | Retina |
| `cornea` | `eye` | Cornea |
| `ear` | `eye_ear` | Ear |
| `inner_ear` | `ear` | Inner ear |

### 3.3 Respiratory
| node_id | parent_region | display_name |
|---|---|---|
| `upper_airway` | `lung_respiratory` | Upper airway |
| `tracheobronchial_tree` | `lung_respiratory` | Trachea / Bronchi |
| `lung` | `lung_respiratory` | Lung |
| `alveolar_lung` | `lung` | Alveolar / parenchymal lung |

### 3.4 Cardiovascular
| node_id | parent_region | display_name |
|---|---|---|
| `heart` | `heart_vascular` | Heart |
| `blood_vessels` | `heart_vascular` | Blood vessels |
| `coronary_system` | `heart` | Coronary system |
| `cerebrovascular_system` | `heart_vascular` | Cerebrovascular system |

### 3.5 Blood / Immune
| node_id | parent_region | display_name |
|---|---|---|
| `blood` | `blood_immune` | Blood |
| `bone_marrow` | `blood_immune` | Bone marrow |
| `lymphatic_system` | `blood_immune` | Lymphatic system |
| `spleen` | `blood_immune` | Spleen |
| `immune_system` | `blood_immune` | Immune system |

### 3.6 Upper GI
| node_id | parent_region | display_name |
|---|---|---|
| `esophagus` | `stomach_upper_gi` | Esophagus |
| `stomach` | `stomach_upper_gi` | Stomach |
| `duodenum` | `stomach_upper_gi` | Duodenum |

### 3.7 Lower GI / Colorectal
| node_id | parent_region | display_name |
|---|---|---|
| `small_intestine` | `intestine_colorectal` | Small intestine |
| `colon` | `intestine_colorectal` | Colon |
| `rectum` | `intestine_colorectal` | Rectum |

### 3.8 Liver / Biliary / Pancreas
| node_id | parent_region | display_name |
|---|---|---|
| `liver` | `liver_biliary_pancreas` | Liver |
| `bile_duct_gallbladder` | `liver_biliary_pancreas` | Bile duct / Gallbladder |
| `pancreas` | `liver_biliary_pancreas` | Pancreas |

### 3.9 Endocrine / Metabolic
| node_id | parent_region | display_name |
|---|---|---|
| `pancreatic_endocrine` | `endocrine_metabolic` | Pancreatic endocrine system |
| `thyroid` | `endocrine_metabolic` | Thyroid |
| `adrenal` | `endocrine_metabolic` | Adrenal |
| `adipose_metabolic_system` | `endocrine_metabolic` | Adipose / metabolic system |

### 3.10 Kidney / Urinary
| node_id | parent_region | display_name |
|---|---|---|
| `kidney` | `kidney_urinary` | Kidney |
| `bladder` | `kidney_urinary` | Bladder |
| `urinary_tract` | `kidney_urinary` | Urinary tract |

### 3.11 Reproductive / Breast
| node_id | parent_region | display_name |
|---|---|---|
| `breast` | `reproductive_breast` | Breast |
| `prostate` | `reproductive_breast` | Prostate |
| `ovary` | `reproductive_breast` | Ovary |
| `uterus_cervix` | `reproductive_breast` | Uterus / Cervix |
| `testis` | `reproductive_breast` | Testis |

### 3.12 Musculoskeletal
| node_id | parent_region | display_name |
|---|---|---|
| `bone` | `bone_joint_muscle` | Bone |
| `joint` | `bone_joint_muscle` | Joint |
| `skeletal_muscle` | `bone_joint_muscle` | Skeletal muscle |

### 3.13 Dermatologic
| node_id | parent_region | display_name |
|---|---|---|
| `skin_surface` | `skin` | Skin |
| `hair_nails` | `skin` | Hair / Nails |

### 3.14 Systemic / Multi-organ
| node_id | parent_region | display_name |
|---|---|---|
| `systemic_multiorgan_core` | `systemic_multiorgan` | Systemic multi-organ |
| `unknown_mixed_site` | `systemic_multiorgan` | Unknown / mixed site |

---

## 4. Anatomy vs Disease Modeling Rule
Anatomy and disease must remain separate.

### Separate concepts
- **anatomy node** = place in the body
- **disease node** = condition or disease concept
- **drug placement** = how a drug maps to anatomy in context

### Required mappings
- `disease -> anatomy`
- `drug -> disease`
- `drug -> body_placement`

### Example
- `glioma` -> `brain`
- `CML` -> `blood` + `bone_marrow`
- `psoriasis` -> `skin_surface`
- `type_2_diabetes` -> `endocrine_metabolic` + `pancreatic_endocrine` + `systemic_multiorgan`

---

## 5. Drug Placement Field Rules
Each drug record should support multiple placement semantics.

```yaml
body_placement:
  primary_disease_site: string
  secondary_disease_sites: [string]
  pharmacology_system: string
  administration_site: string | null
  systemic_flag: boolean
  placement_basis: string
```

### Meaning
- `primary_disease_site` = best visible body anchor for the user
- `secondary_disease_sites` = additional relevant body contexts
- `pharmacology_system` = system-level pharmacological context
- `administration_site` = route/site of administration if relevant
- `systemic_flag` = true when action/use is fundamentally systemic or multi-organ
- `placement_basis` = why this placement was chosen

### Allowed `placement_basis` values
- `disease_location`
- `clinical_use_system`
- `pharmacology_system`
- `administration_site`
- `mixed_rule`

---

## 6. Placement Authority Rules
When multiple placements are possible, resolve in this order:
1. **disease location**
2. **clinical use system**
3. **pharmacology system**
4. **administration site**

### Examples
- glioma drug -> `brain_cns`
- lung cancer drug -> `lung_respiratory`
- CML drug -> `blood_immune`
- reflux drug -> `stomach_upper_gi`
- systemic corticosteroid -> `systemic_multiorgan` unless a specific disease context is being shown

---

## 7. Disease-to-Anatomy Mapping Examples

| disease / indication | mapped visible region | mapped internal node(s) |
|---|---|---|
| Glioma | `brain_cns` | `brain`, `cerebrum` |
| Alzheimer’s disease | `brain_cns` | `brain` |
| Epilepsy | `brain_cns` | `brain` |
| Glaucoma | `eye_ear` | `eye` |
| Asthma | `lung_respiratory` | `tracheobronchial_tree` |
| COPD | `lung_respiratory` | `lung`, `tracheobronchial_tree` |
| NSCLC | `lung_respiratory` | `lung` |
| Hypertension | `heart_vascular` | `blood_vessels` |
| Hyperlipidemia | `heart_vascular` | `blood_vessels`, `systemic_multiorgan_core` |
| CML | `blood_immune` | `blood`, `bone_marrow` |
| Lymphoma | `blood_immune` | `lymphatic_system` |
| GERD | `stomach_upper_gi` | `esophagus`, `stomach` |
| Peptic ulcer disease | `stomach_upper_gi` | `stomach`, `duodenum` |
| Crohn’s disease | `intestine_colorectal` | `small_intestine`, `colon` |
| Ulcerative colitis | `intestine_colorectal` | `colon`, `rectum` |
| Hepatocellular carcinoma | `liver_biliary_pancreas` | `liver` |
| Type 2 diabetes | `endocrine_metabolic` | `pancreatic_endocrine`, `adipose_metabolic_system` |
| Hypothyroidism | `endocrine_metabolic` | `thyroid` |
| CKD | `kidney_urinary` | `kidney` |
| BPH | `reproductive_breast` | `prostate` |
| Breast cancer | `reproductive_breast` | `breast` |
| Osteoarthritis | `bone_joint_muscle` | `joint` |
| Osteoporosis | `bone_joint_muscle` | `bone` |
| Psoriasis | `skin` | `skin_surface` |
| Systemic lupus erythematosus | `systemic_multiorgan` | `immune_system`, `systemic_multiorgan_core` |

---

## 8. Systemic Drug Handling Rules
Some drugs should not be forced into a single-organ model.

### Rule
Systemic drugs should use:
- a **primary visible site** when a disease context is dominant
- plus `systemic_flag = true`
- and optionally `secondary_disease_sites`

### Examples
- **Osimertinib**:
  - primary_disease_site = `lung_respiratory`
  - systemic_flag = true
- **Metformin**:
  - primary_disease_site = `endocrine_metabolic`
  - secondary_disease_sites = [`liver_biliary_pancreas`]
  - systemic_flag = true
- **Prednisone**:
  - primary_disease_site = `systemic_multiorgan`
  - systemic_flag = true

---

## 9. UI Interaction Implications
Module 2 must support the agreed UX:
- ATC filter first
- body-region hover for preview
- click to lock region
- preview and detail cards depend on intersection of ATC + body region

### Preview behavior
- Hover over visible region for ~1-2 seconds
- Show drugs matching current ATC filter + hovered region
- If no ATC filter is active, region can still preview all mapped drugs

### Future drill-down
Later versions may allow:
- `brain_cns` -> `brain` -> disease-specific subcontexts
- `lung_respiratory` -> `lung` / `airway`
- `blood_immune` -> `blood` / `bone_marrow` / `lymphatic_system`

---

## 10. Special Modeling Decisions (Locked)
- **Breast** is modeled internally as its own node under `reproductive_breast` and may become a standalone visible region later.
- **Liver and pancreas** are grouped visually at first, but remain separate internal nodes.
- **Bone marrow** remains an internal node under `blood_immune`.
- **GI is visibly split** into `stomach_upper_gi` and `intestine_colorectal`.
- **Systemic / multi-organ** remains a visible region because many important drug classes require it.

---

## 11. Implementation Notes
- Store visible-region ids and internal node ids separately when useful.
- The frontend body map should bind to **visible region ids**.
- Disease curation can later map to finer internal nodes without changing the top-level UI.
- Do not over-specialize Level 3 disease-site nodes in the earliest implementation; keep room for later refinement.

---

## 12. Open Follow-up for Module 3
Body Ontology v1 defines where drugs and diseases sit anatomically.
Next, **Module 3 — Curation Rules v1** should define:
- what records qualify for v1
- trusted sources and priority
- conflict resolution
- lineage-confidence rules

*Updated: 2026-03-13 17:02*
*Version: 1.0 (Body Ontology v1 drafted inside master plan)*

---

# Module 3 — Curation Rules v1

## 1. Purpose
Curation Rules v1 defines what data is allowed into DrugTree, which sources are trusted, and how conflicts are resolved.

It exists to prevent:
- noisy records
- mixed-quality structures
- unclear lineage claims
- inconsistent placement
- schema drift during expansion

---

## 2. Scope for v1

### Inclusion Rule (Locked)
**DrugTree v1 should include approved small-molecule drugs only.**

### Excluded from strict v1
- biologics
- peptides
- antibodies
- cell therapies
- gene therapies
- radiopharmaceutical edge cases unless intentionally curated later
- phase I/II/III candidates (deferred to later phase)

### Why
This keeps v1:
- chemically coherent
- easier to render and compare
- easier to classify into scaffold/lineage families
- more useful for medicinal chemistry users

---

## 3. Record Eligibility Rules
A drug record is eligible for v1 only if all of the following are true:

### Mandatory eligibility
1. **Approved drug** in at least one major regulatory context or clearly established approved-market status
2. **Small molecule** with a definable chemical structure
3. Has a **valid SMILES or equivalent structure identity**
4. Has at least one **assignable therapeutic use / indication**
5. Has at least one **ATC classification** or a curatable equivalent
6. Can be mapped to at least one **body placement** using Module 2 rules

### Preferably present
- InChIKey
- approval year
- known target or mechanism
- drug class
- company or historical sponsor

### Temporary hold / quarantine
If a record lacks one of the mandatory fields above, it should not enter the public dataset yet.
It may be stored in a **staging / review pool** later, but not in the main displayed dataset.

---

## 4. Source Priority Rules
When multiple sources disagree, use this priority order by field type.

### 4.1 Structure identity fields
For:
- SMILES
- InChIKey
- molecular weight
- structural identifiers

**Priority:**
1. PubChem
2. ChEMBL
3. DrugBank
4. curated manual correction

### 4.2 Classification fields
For:
- ATC code
- ATC level 1 label
- pharmacologic class

**Priority:**
1. WHO ATC / official ATC references
2. DrugBank
3. curated manual classification

### 4.3 Clinical fields
For:
- indications
- treatment summary
- disease area
- approval context

**Priority:**
1. official label / regulatory summary where available
2. DrugBank
3. ChEMBL / PubChem summaries
4. curated summary

### 4.4 Biology fields
For:
- target(s)
- mechanism
- pathway

**Priority:**
1. curated canonical target assignment
2. ChEMBL
3. DrugBank
4. PubChem summaries

### 4.5 Timeline / company fields
For:
- approval year
- sponsor/company

**Priority:**
1. official/regulatory record if easy to confirm
2. DrugBank
3. curated trusted secondary source

---

## 5. Conflict Resolution Rules

### Structure conflicts
If sources disagree on SMILES/InChIKey:
- prefer PubChem
- verify against ChEMBL
- if conflict remains unresolved, mark record for review and keep out of public dataset

### ATC conflicts
If multiple ATC codes exist:
- keep the **primary clinically representative code** for MVP
- store alternates later when schema expands
- ATC level 1 should reflect the selected primary code

### Indication conflicts
If a drug has many uses:
- choose one **primary disease area** for Public Mode summary
- keep multiple `specific_indications`
- preserve broader therapeutic reality in Scientist Mode

### Target conflicts
If many targets are reported:
- keep **canonical clinically relevant targets** in v1
- defer broad off-target lists to later

### Placement conflicts
Use **Module 2 placement authority rules**:
1. disease location
2. clinical use system
3. pharmacology system
4. administration site

---

## 6. Missing Data Rules

### Allowed missing in MVP
These may be null without blocking inclusion:
- name_zh
- clogp
- tpsa
- hba/hbd
- rotatable bonds
- scaffold_core
- pathway
- lineage family ids
- clinicaltrials refs

### Not allowed missing in MVP
These should block public inclusion if absent:
- name_en
- ATC code or curatable primary classification
- primary indication summary
- primary body placement
- SMILES or equivalent structure identity
- molecular identity key (preferably InChIKey)

---

## 7. Small-Molecule Boundary Rules
For v1, the following are considered **in scope**:
- classical oral small molecules
- synthetic drugs
- natural-product-derived small molecules
- contrast agents if structurally defined and therapeutically relevant

The following are **out of scope** for v1:
- monoclonal antibodies
- recombinant proteins
- oligonucleotides
- ADCs
- CAR-T / cell products
- vaccines

### Borderline rule
If a compound is technically not a small molecule or is difficult to represent as a standard medicinal-chemistry structure card, exclude it from v1.

---

## 8. Lineage and Family Curation Rules
DrugTree should be conservative about relationship claims.

### Scaffold family display rule
Display a scaffold-family relationship if there is a clear medicinal-chemistry common core or well-accepted chemical family.

### Target family display rule
Display a target-family relationship if drugs share a clearly recognized primary target class.

### Lineage family display rule
Display a lineage relationship only if at least one of the following is true:
1. it is widely recognized historically as a next-generation / follow-on drug
2. medicinal-chemistry evolution is clear and defensible
3. resistance-driven succession is well established

### If uncertain
- keep the drug record
- leave family id null
- do not force a speculative lineage

This is important. False genealogy is worse than incomplete genealogy.

---

## 9. Public Summary Curation Rule
Each drug should have a one-sentence **Public Mode summary**.

### Style rule
It should be:
- plain-language
- accurate
- non-promotional
- short enough for cards

### Example style
- “A targeted anti-cancer drug used mainly for leukemia and certain tumors.”
- “A stomach-acid reducing drug used for reflux and ulcer treatment.”
- “A diabetes medicine used to improve blood sugar control.”

### Avoid
- jargon-heavy phrasing
- marketing language
- mechanism-only descriptions with no clinical meaning

---

## 10. Provenance Rule
Every important record should preserve a lightweight source trail.

### Minimum expectation in v1
Each drug should store at least one or more source objects covering:
- structure source
- classification source
- indication source

### If a field is manually curated
Mark it as:
- `source_name: curated`
- with a note explaining the rationale when needed

---

## 11. Quality Tiers for Records
To support iterative buildout, use three internal quality tiers.

### Tier A — ready for public display
Has:
- valid structure identity
- stable ATC classification
- usable indication summary
- body placement
- evidence trail

### Tier B — usable but incomplete
Has:
- valid structure + class + indication
- missing some expert descriptors
- still acceptable for MVP if core fields are present

### Tier C — review only
Has:
- unresolved conflict
- weak placement
- unclear approval status
- uncertain structure mapping

Only **Tier A/B** should appear in the public app.

---

## 12. MVP Dataset Target
Recommended first implementation target:
- **100-200 approved small molecules**
- distributed across all 14 ATC Level 1 groups
- with reliable structure identity
- with body placement
- with simple public summaries
- with at least 5-10 defensible lineage families for later expansion

This is enough to feel real without overextending curation effort.

---

## 13. Implementation Notes
- Maintain one canonical dataset, not separate public/expert datasets.
- Allow nulls for advanced chemistry fields in early iterations.
- Keep speculative relationships out until confidence is good.
- Prefer fewer high-quality records over many weak records.

---

## 14. Open Follow-up for Module 4
After Curation Rules v1, the next module should define exact UI behavior and filter logic:
**Module 4 — Interaction Spec v1**.

*Updated: 2026-03-13 17:08*
*Version: 1.1 (Curation Rules v1 drafted inside master plan)*

---

# Module 4 — Interaction Spec v1

## 1. Purpose
Interaction Spec v1 defines the exact user-facing behavior of DrugTree for the MVP and early post-MVP iterations.

It must make the experience:
- intuitive for Public users
- information-dense but readable for Scientist users
- consistent across ATC filtering, body navigation, and detail exploration

---

## 2. Core Interaction Model
DrugTree uses a **dual-filter atlas** interaction model:

1. **ATC label filter** narrows the therapeutic universe
2. **Body-region interaction** refines the spatial/clinical context
3. **Drug cards** present matching results
4. **Detail panel/modal** reveals deeper information
5. **Mode switch** changes presentation depth, not dataset

### Canonical user flow
- choose ATC filter
- hover body region for preview
- click body region to lock
- browse result cards
- open one card for full detail
- switch between Public / Scientist mode as needed

---

## 3. Global UI Controls
The MVP interface should contain these persistent controls:

### Top bar
- project title / logo
- search box
- mode switch: `Public | Scientist`
- reset / clear filters button

### Left-side or top filter area
- ATC Level 1 filter buttons
- optional “All ATC” state

### Main visual panel
- human body map with visible regions from Module 2

### Results panel
- dynamic list/grid of drug cards

### Detail layer
- modal or side panel for selected drug

---

## 4. Mode Switch Behavior

### Public Mode (default)
Public Mode should show:
- drug name
- short treatment summary
- ATC label
- primary body region context
- approval year/status
- small structure thumbnail

Public Mode should hide or collapse:
- raw SMILES
- InChIKey
- detailed physicochemical descriptors
- family ids
- deep lineage notes
- verbose target technicals

### Scientist Mode
Scientist Mode should show:
- all Public fields
- structure emphasis
- drug class
- targets
- mechanism
- SMILES / InChIKey
- MW / cLogP / TPSA / HBA / HBD / rotatable bonds when available
- family / lineage blocks
- evidence sources

### Rule
Mode switching must **not reload a different dataset**.
It only changes field visibility and detail density.

---

## 5. ATC Filter Behavior

### States
ATC filter can be in one of these states:
- **None selected** = all ATC groups visible
- **One selected** = hard filter to that therapeutic class
- future extension: multi-select (not required in MVP)

### Rule
For MVP, ATC should be **single-select** for clarity.

### UI behavior
- clicking an ATC button selects it
- clicking the same ATC button again clears it
- selecting a new ATC replaces the old one

### Result logic
- if ATC selected + no body region selected: show all drugs in that ATC filter
- if ATC selected + body region hovered: preview intersection
- if ATC selected + body region locked: show locked intersection

---

## 6. Body Region Interaction Behavior

### Hover preview
- hover delay: **~1.0-1.5 seconds** (target default: **1.2s**)
- after dwell threshold is reached, show preview results for that region
- preview should respect the current ATC filter if one is active

### Click to lock
- clicking a body region locks it as the active spatial filter
- locked region remains active until:
  - another region is clicked
  - filters are reset
  - user clicks same locked region again to unlock (recommended)

### Hover vs locked priority
- **locked region overrides hover previews**
- if region is locked, casual hover on other regions should not replace the locked result set unless explicitly allowed later

### Visual states
Each region should support these visual states:
- default
- hover-preview
- locked-selected
- muted-by-filter

---

## 7. Search Behavior

### MVP search scope
Search should match against:
- drug name
- synonyms
- brand names
- optional ATC code text

### Search precedence
Search acts as a **refinement layer** on top of current ATC/body filters.

### Logic
Final results =
`search matches` ∩ `ATC filter` ∩ `body filter`

### Empty query
If search box is empty, do not constrain results.

---

## 8. Result Card Behavior

### Public card default
Show:
- small 2D structure thumbnail
- drug name
- brief summary
- ATC mini-tag
- primary indication / body-region cue
- approval year

### Scientist card default
Show:
- structure thumbnail
- drug name
- ATC mini-tag
- drug class
- primary target(s)
- approval year
- one or two compact expert descriptors (e.g. MW)

### Card density rule
Scientist Mode should be **compact expert**, not full-detail by default.
Full chemistry appears after click/expand.

---

## 9. Detail Panel / Modal Behavior

### Trigger
- click a drug card → open detail panel or modal

### Public detail view
Show:
- drug name
- brand names / common synonyms
- larger structure image
- what it treats
- where it maps in body
- ATC class
- approval year/status
- simple mechanism sentence

### Scientist detail view
Show Public detail plus:
- SMILES
- InChIKey
- physicochemical descriptors
- targets
- mechanism
- scaffold / lineage section
- provenance / source links

### Progressive disclosure
Even in Scientist Mode, advanced chemistry blocks should be collapsible.

---

## 10. Empty-State Behavior
Empty states must be informative, not silent.

### Cases
1. **No ATC / no region / no search**
   - show featured or recent drug list
   - encourage user to choose ATC or body region

2. **ATC selected but no body region yet**
   - show all drugs in ATC category
   - prompt user to refine by body region

3. **ATC + body intersection empty**
   - show “No drugs matched this combination”
   - suggest nearby regions or clear one filter

4. **Search produces no result**
   - show search-empty message
   - preserve current filters visually

---

## 11. Systemic Drug UI Rules
Systemic drugs must remain understandable in the interface.

### Rule
A systemic drug can still have a visible primary region if disease context is strong.

### Display behavior
If `systemic_flag = true`:
- show a **systemic badge/tag** on the card
- keep primary body anchor visible
- optionally show secondary regions in detail view

### Example
- Metformin → endocrine/metabolic + systemic badge
- Osimertinib → lung/respiratory + systemic badge
- Prednisone → systemic/multi-organ primary view unless context-specific page overrides

---

## 12. Reset Behavior
The interface should include a clear reset model.

### Reset all
A `Clear Filters` action should reset:
- ATC selection
- locked body region
- search query
- result set back to default state

### Partial reset behavior
- clicking same ATC again clears ATC
- clicking same locked body region again unlocks it
- clearing search removes only search constraint

---

## 13. Default Landing State
When the page first opens:
- mode = **Public**
- ATC = none selected
- body region = none locked
- search = empty
- results = featured representative drugs OR alphabetic starter set

### Recommended starter state
Show:
- a brief instruction line
- a few representative drugs across categories
- visible ATC buttons
- highlighted invitation to hover the body map

---

## 14. Future Extensions (not required in MVP)
- multi-select ATC filters
- body-region drill-down
- compare mode
- family lineage side panel
- target-centric exploration
- substructure / similarity search
- user-pinned favorites

---

## 15. Implementation Notes
- Keep interaction logic deterministic and easy to explain.
- Prefer explicit state objects in frontend code:
  - `selectedATC`
  - `hoveredRegion`
  - `lockedRegion`
  - `searchQuery`
  - `uiMode`
- Avoid hidden logic that changes behavior unpredictably.

---

## 16. Planning Status
With Module 4 complete, the core design set inside `PROJECT_PLAN.md` now includes:
1. Schema v1
2. Body Ontology v1
3. Curation Rules v1
4. Interaction Spec v1

This is sufficient to begin structured implementation work.

*Updated: 2026-03-13 17:13*
*Version: 1.2 (Interaction Spec v1 drafted inside master plan)*

---

## 🎨 Visual Direction Pivot — Central Body Atlas (2026-03-13)

### Why this update exists
The current implementation works functionally, but its visual hierarchy does **not** match the intended product identity.

### Current layout problem
The current UI behaves like a conventional:
- sidebar filters
- small body map
- results panel

That makes the body map feel secondary.

### Desired product feeling
DrugTree should feel like:
- a **body-centered medical atlas**
- with **floating ATC labels/tags** around the body
- where tags are **anchored to tissues / disease-relevant regions**
- and the body is the **main hero visual** in the center of the page

This is now the preferred visual direction.

---

### New Layout Principle (Locked)
The page should be restructured into:

1. **Header layer**
   - logo / title
   - search
   - Public / Scientist switch
   - clear filters / reset

2. **Atlas hero section**
   - large human body centered on page
   - floating ATC tags around the body
   - spatial anchoring of tags to relevant tissue/disease contexts

3. **Results section**
   - filtered drug cards below the atlas
   - cards should not compete with the hero body visual

### Important layout change
The body map is no longer a sidebar widget.
It is the **central organizing visual** of the page.

---

### Floating ATC Tag Concept
ATC categories should no longer be rendered as a plain vertical button list.

Instead, they should appear as:
- floating tags / pills / chips
- placed around the body
- visually associated with specific anatomical regions
- still clickable as filters

### Example anchoring logic
- **N / Nervous System** near brain / CNS
- **R / Respiratory** near lungs
- **C / Cardiovascular** near heart / vessels
- **A / Alimentary & Metabolism** near stomach / liver / pancreas context
- **L / Antineoplastic** near blood / immune / disease hotspot contexts
- **D / Dermatological** near skin
- **G / Genito-urinary** near pelvic region
- **M / Musculo-skeletal** near bone / joint / muscle regions

These tags are both:
- **filters**
- **visual atlas elements**

---

### Revised Interaction Model
The interaction model remains dual-filter, but becomes more spatially expressive:

1. User sees **large centered body** on first load
2. User hovers/clicks **floating ATC tag**
3. Corresponding body region(s) glow or highlight
4. User hovers/clicks body region for refinement
5. Matching drugs appear below
6. Clicking a drug opens detail view

### Updated UX emphasis
- body first
- ATC around body
- results below
- detail on click

---

### Visual Hierarchy Rules (Locked)
1. **Human body is the hero visual**
2. **ATC tags are secondary but spatially coupled to the body**
3. **Drug cards are tertiary and live below the atlas**
4. Filtering should feel like activating a living map, not using a sidebar form

---

### Atlas Section Style Direction
The atlas hero section should feel immersive and clean.

#### Style goals
- darker or atmospheric background in atlas zone
- subtle glow/highlight on active tissues
- floating ATC tags with category colors
- high contrast around body silhouette
- elegant medical / scientific tone, not dashboard-like

#### Recommended visual language
- dark gradient or deep neutral background
- luminous highlights for active regions
- soft motion on hover
- compact but expressive ATC tag pills

---

### Body Map Behavior Update
The body SVG should be redesigned or resized for hero usage.

#### Requirements
- significantly larger central body illustration
- clear regional hotspots
- enough visual simplicity for quick recognition
- enough precision to support anchored tags

#### Region behavior
- hover region -> preview state
- click region -> locked state
- active ATC tags should visually connect to relevant region(s)

Optional later enhancement:
- subtle connection lines or halo effects between ATC tags and body regions

---

### ATC Tag Behavior Update
Each ATC tag should support:
- default floating state
- hover glow
- selected / locked state
- muted state when incompatible with current filter context

#### Tag interactions
- hover tag -> highlight relevant region(s)
- click tag -> activate ATC filter
- click again -> clear ATC filter

### Tag content (recommended)
Each tag can show:
- ATC code letter
- short label or abbreviation
- optional icon
- optional count badge in later iterations

---

### Results Section Update
Drug cards should move below the hero atlas.

#### Rule
Results should support the atlas, not visually overpower it.

#### Card presentation
- compact cards in Public mode
- compact-expert cards in Scientist mode
- results grid below atlas section
- empty-state guidance if no filter combination matches

---

### Technical Frontend Direction
Implementation should move away from a sidebar-driven layout toward an atlas-driven layout.

#### Frontend implications
Recommended structure:
- `header`
- `atlas-section`
- `results-section`
- `detail-modal`

Possible CSS/JS organization:
- base styles
- atlas layout styles
- floating tag styles
- atlas interaction controller

### State model remains valid
Existing state concepts still apply:
- selected ATC
- hovered region
- locked region
- search query
- UI mode

Only the visual orchestration changes.

---

### Updated Success Criteria
The next implementation round should succeed only if:
- the body is clearly the central focal element
- ATC labels feel spatially anchored, not detached filters
- the page feels like a medical atlas, not a filter dashboard
- filtering still works cleanly
- Public / Scientist modes remain intact
- the layout remains readable on large desktop screens first

---

### Priority for next manual implementation round

#### P0
- replace sidebar layout with centered atlas layout
- enlarge body map significantly
- move ATC filters into floating anchored tags
- move results grid below atlas

#### P1
- improve hero background / atmosphere
- improve tissue highlight behavior
- improve hover / lock transitions

#### P2
- add connection lines / halos
- responsive tablet/mobile adaptation
- count badges / richer tag metadata

---

### Planning impact
This update does **not** replace Modules 1-4.
It changes the **presentation architecture** sitting on top of them.

In other words:
- Schema v1 stays valid
- Body Ontology v1 stays valid
- Curation Rules v1 stay valid
- Interaction Spec v1 stays valid
- but the **visual composition** is now explicitly atlas-centered

*Updated: 2026-03-13 17:53*
*Version: 1.3 (Central Body Atlas visual direction locked)*
