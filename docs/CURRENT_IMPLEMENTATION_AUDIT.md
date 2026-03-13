# DrugTree Current Implementation Audit

_Date: 2026-03-13_

## Scope
This audit compares the current implementation against the markdown files in `docs/`:
- `docs/CENTRAL_BODY_ATLAS_IMPLEMENTATION.md`
- `docs/PROJECT_PLAN.md`
- `docs/PROGRESS_SUMMARY.md`

## Status Legend
- ✅ Implemented
- 🟡 Partial / inconsistent
- ❌ Missing / not aligned
- ℹ️ Note / doc drift

## Executive Summary
The **Central Body Atlas shell is implemented**: top bar, centered atlas stage, floating ATC tags, active filters bar, results grid, and modal all exist in the frontend. However, the implementation is still **partial** relative to the more detailed requirements in `PROJECT_PLAN.md`, especially for **dual-filter behavior (ATC + body together)**, **Public vs Scientist detail tiers**, **body ontology integration**, and **schema depth**.

The biggest visual issue is the body itself: the current visible body is **not driven by `src/frontend/assets/human-body.svg`**. Instead, `src/frontend/js/app.js` programmatically draws a simplified inline SVG body map. So the current `human-body.svg` is both **low quality** and **not actually wired into the rendered atlas**.

---

## Checklist

### 1) Central Body Atlas layout
| Item | Doc source | Status | Current implementation | Notes / TODO |
|---|---|---:|---|---|
| Top bar with brand, search, clear, mode switch | Central Body Atlas Guide §4 | ✅ | Present in `src/frontend/index.html` | Good baseline |
| Body as hero visual in center | Central Body Atlas Guide §1-4 | 🟡 | Atlas container exists, but body rendering is a simplistic generated SVG in `src/frontend/js/app.js` | Replace with a higher-quality anatomical asset / integrated hotspot layer |
| Floating ATC tags around body | Central Body Atlas Guide §4-5 | ✅ | 14 `.atc-tag` buttons in `index.html`, positioned in `style.css` | Layout exists |
| Results below atlas, not beside it | Central Body Atlas Guide §1-4 | ✅ | Implemented in `index.html` | Aligned |
| Active filters bar | Central Body Atlas Guide §4 | ✅ | Present and dynamically updated by `updateActiveFiltersBar()` | One remove-button typo remains (`&times;}`) |
| Detail modal / panel on click | Central Body Atlas Guide §4 | ✅ | Implemented as modal in `index.html` + `app.js` | Aligned |
| Dark atlas styling | Central Body Atlas Guide §5 | ✅ | Implemented in `src/frontend/css/style.css` | Overall style direction matches |
| Luminous glow around body | Progress Summary / AGENTS / Atlas Guide | 🟡 | `index.html` includes `.atlas-glow`, but there is no matching CSS rule; the visible glow mostly comes from background and other styles | Add a real glow layer if this effect is still desired |

### 2) ATC filtering and search
| Item | Doc source | Status | Current implementation | Notes / TODO |
|---|---|---:|---|---|
| 14 ATC categories | AGENTS / Progress Summary | ✅ | 14 categories defined in `app.js` and rendered in `index.html` | Aligned |
| Single-select ATC filtering | PROJECT_PLAN Module 4 §5 | ✅ | `filterByCategory()` toggles one active category | Aligned |
| Hover preview on ATC tags | PROJECT_PLAN Module 4 §5-6 | ✅ | Implemented with `hoverDelay = 1200` ms and preview tooltip | Aligned |
| Search refines results | PROJECT_PLAN Module 4 §7 | ✅ | `setupSearch()` + `applyFilters()` intersect search with current filters | Works at code level |
| “All ATC” / no filter state | PROJECT_PLAN Module 4 §3/5 | 🟡 | Logic uses `'all'`, but initial state starts as `null` rather than `'all'` | Initialize explicitly to avoid inconsistent initial UI/count text |

### 3) Body-region interaction
| Item | Doc source | Status | Current implementation | Notes / TODO |
|---|---|---:|---|---|
| Hover preview on body regions | PROJECT_PLAN Module 4 §6 | ✅ | Implemented in `handleBodyRegionHover()` / `showBodyPreview()` | Delay matches target |
| Click region to lock | PROJECT_PLAN Module 4 §6 | 🟡 | Clicking sets `activeBodyRegion` | Lock exists, but interaction model is incomplete |
| Click same locked region again to unlock | PROJECT_PLAN Module 4 §6 | ❌ | Not implemented | Add toggle-off behavior |
| Locked region should coexist with ATC filter | PROJECT_PLAN Module 4 §2/5/6 | ❌ | `filterByBodyRegion()` resets `activeCategory = 'all'` | This breaks the documented dual-filter atlas model |
| Locked region should override casual hover | PROJECT_PLAN Module 4 §6 | ❌ | Hover previews still run even when a region is active | Add locked-state priority rules |
| Visual states: default / hover / locked / muted | PROJECT_PLAN Module 4 §6 | 🟡 | Default, hover, and active exist; muted-by-filter is not implemented for body regions | Add filter-aware region states |
| Human body should be recognizably anatomical | Atlas Guide / user note | ❌ | Current generated paths are abstract blobs; `assets/human-body.svg` is cartoonish and unused | Rebuild the body asset and integrate it into the rendered atlas |

### 4) Public vs Scientist mode
| Item | Doc source | Status | Current implementation | Notes / TODO |
|---|---|---:|---|---|
| Mode switch exists | PROJECT_PLAN Module 4 §3-4 | ✅ | Buttons and switch logic exist | Aligned |
| Mode switch should change detail density, not dataset | PROJECT_PLAN Module 4 §4 | ✅ | Same dataset, different mode state | Aligned at a high level |
| Public cards should stay simplified | PROJECT_PLAN Module 4 §8 | 🟡 | Card layout is compact, but identical in both modes | Add real public/scientist card variants |
| Scientist mode should reveal more chemistry/biology fields | PROJECT_PLAN Module 4 §4/8/9 | 🟡 | Only genealogy is explicitly mode-gated; most card/modal content is the same in both modes | Add InChIKey, descriptors, mechanism, evidence, etc. in Scientist mode |
| Public mode should hide raw SMILES / technical fields | PROJECT_PLAN Module 4 §4 | ❌ | SMILES is always visible in the modal | Move SMILES and other technical fields behind Scientist mode |

### 5) Data model and ontology alignment
| Item | Doc source | Status | Current implementation | Notes / TODO |
|---|---|---:|---|---|
| Rich nested schema (`identity`, `classification`, `clinical`, `body_placement`, `chemistry`, `biology`, `development`, `evidence`) | PROJECT_PLAN Module 1 | ❌ | Current frontend/backend still use a flat record shape (`id`, `name`, `atc_category`, `class`, etc.) | Decide whether to migrate data shape now or add a translation layer |
| Required MVP fields such as treatment summary, body placement, mechanism, evidence sources | PROJECT_PLAN Module 1 §4 | ❌ | Many of these fields are absent in current JSON and UI | Expand ETL/schema or downgrade docs to actual scope |
| Body ontology integration | PROJECT_PLAN Module 2 / `data/ontology/body_ontology.json` | ❌ | Ontology file exists, but frontend uses hardcoded `getDrugBodyRegions()` mappings | Replace hardcoded region mapping with ontology-driven mapping |
| 14 visible body regions from ontology | PROJECT_PLAN Module 2 | 🟡 | Current body map uses custom region ids like `head`, `eyes`, `liver`, `immune`, etc. | Region model does not match ontology ids such as `brain_cns`, `heart_vascular`, etc. |

### 6) Backend / data delivery
| Item | Doc source | Status | Current implementation | Notes / TODO |
|---|---|---:|---|---|
| Backend exists | Progress Summary | ✅ | `src/backend/` with FastAPI app, router, models, ETL exists | Aligned |
| Expanded 1,508-drug dataset exists | Progress Summary | ✅ | `src/frontend/data/drugs.json` and `drugs-expanded.json` both exist | Aligned |
| Frontend can load backend API | Progress Summary | ✅ | `app.js` fetches `/api/v1/drugs?limit=2000` | Aligned |
| Health endpoint should reflect expanded dataset | Progress Summary Known Issues | 🟡 | `src/backend/main.py` still loads `drugs-full.json`, so health reports 61 | Fix data path to `drugs.json` |
| Offline/local fallback should use expanded dataset | Progress Summary / practical expectation | 🟡 | Fallback still loads `data/drugs-full.json` before sample data | Change fallback order to prefer `data/drugs.json` |
| Progress summary API path examples are current | Progress Summary | ℹ️ | Docs mention `/api/drugs` and `/api/stats`, but actual routes are `/api/v1/drugs` and `/api/v1/stats` | Update docs to avoid confusion |

### 7) Asset and dead-code cleanup
| Item | Doc source | Status | Current implementation | Notes / TODO |
|---|---|---:|---|---|
| `human-body.svg` should be the central asset | Central Body Atlas Guide DOM example | ❌ | Current DOM no longer uses `<img src="assets/human-body.svg">` | Reintegrate asset or remove stale expectation from docs |
| Legacy body-map loader should match current DOM | N/A (implementation consistency) | ❌ | `src/frontend/js/body-map.js` expects an embedded SVG object with `contentDocument`, which is not how `index.html` is structured now | Remove or refactor dead legacy code |
| Body label elements referenced in JS should exist | Implementation consistency | ❌ | `app.js` references `#body-region-label`, but no such element exists in `index.html` | Add label element or delete dead code paths |

---

## Priority TODOs

### P1 — should be fixed next
1. **Restore the documented dual-filter behavior** so body-region selection does not clear the active ATC filter.
2. **Replace the current generated body blobs** with a better-designed anatomical body asset/hotspot system.
3. **Wire the rendered atlas to the actual body asset**; right now rebuilding `src/frontend/assets/human-body.svg` alone will not change the UI.
4. **Use the ontology file** (`data/ontology/body_ontology.json`) instead of hardcoded body-region mappings in `app.js`.
5. **Make Public vs Scientist mode meaningfully different**, especially by hiding SMILES/technical fields in Public mode and revealing deeper details in Scientist mode.

### P2 — should follow after the core interaction fix
6. Change frontend local fallback from `drugs-full.json` to `drugs.json`.
7. Fix backend `main.py` health data source to `drugs.json`.
8. Remove or refactor legacy `src/frontend/js/body-map.js`.
9. Align region ids in the UI with ontology region ids.
10. Fix small UI inconsistencies (e.g. filter-chip remove button typo, initial `activeCategory` state).

### P3 — documentation and scope cleanup
11. Update `docs/PROGRESS_SUMMARY.md` to match actual API paths and current implementation gaps.
12. Decide whether the project will migrate to the richer nested schema in `PROJECT_PLAN.md`, or whether the docs should be narrowed to the currently implemented flat schema.

---

## Notes
- The current implementation reflects the **layout direction** in `CENTRAL_BODY_ATLAS_IMPLEMENTATION.md`, but not yet the full **interaction/system design** from the later modules in `PROJECT_PLAN.md`.
- There is **doc drift** inside `PROJECT_PLAN.md` itself: older sections describe an 8-category simplified body map, while later modules define the richer 14-category atlas and ontology. The later modules appear to be the better target for current work.
- The current visible body is generated in `src/frontend/js/app.js`; this is why the body looks abstract even though `src/frontend/assets/human-body.svg` exists.
- For the SVG redesign specifically, the new asset should probably target:
  - a clean front-facing human silhouette,
  - dark-atlas friendly styling,
  - no baked-in emoji/text labels,
  - separate hotspot/region overlays,
  - compatibility with the 14-region ontology.

## Suggested next action for the body SVG
Before rebuilding `src/frontend/assets/human-body.svg`, confirm the preferred direction for the new body artwork:
1. **Minimal anatomical silhouette** (clean, elegant, atlas-like)
2. **Semi-anatomical medical illustration** (organs subtly indicated)
3. **Glow-outline sci-med body** (stylized, futuristic atlas look)

My recommendation is **Option 1 or 2**, because they fit the existing dark atlas UI better than the current cartoon-style asset and will be easier to align with the ontology-driven hotspot layer.
