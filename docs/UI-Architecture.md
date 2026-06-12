# DrugTree UI Architecture

**Status:** Living document · **Last reviewed:** 2026-06-12 (branch `main`, base commit `34933f0`, with uncommitted two-pane refactor in the working tree)
**Audience:** Anyone optimizing or extending the frontend.
**Companion:** [Architecture.md](./Architecture.md) covers the backend/data layer. For an exhaustive state inventory see [frontend-state-model.md](./ui/frontend-state-model.md) (note: its "Drug Modal / B6" sections predate the current anchored detail-page surface — see §7 below).

This document is the frontend map: the shell, the module graph, the state model, the render pipeline, and the seams to optimize. It reflects the **in-progress two-pane workspace refactor** currently in the working tree.

---

## 1. Philosophy & Constraints

- **Vanilla JS, no framework, no build step.** Everything loads as global `<script>` tags. There is no bundler, no JSX, no module system at runtime. Keep this unless a deliberate decision changes it.
- **API-first, embed-fallback.** The app tries the backend (`/api/v1/*`), then falls back to generated `src/frontend/data/*.js` embeds. It must remain fully usable with no backend (GitHub Pages).
- **One canonical dataset, two presentation modes.** Public mode (treatment-focused) and Scientist mode (chemistry/lineage-rich) read the same records and differ only in disclosed fields.
- **Progressive disclosure.** Shell data first (fast paint), full records hydrated on demand, structures rendered lazily on scroll.

---

## 2. Shell & Layout

The current layout (post-refactor) is a **two-pane workspace**: a sticky atlas on the left, a scrollable results/detail panel on the right.

```
┌───────────────────────────────────────────────────────────────┐
│ .topbar  [DrugTree] [Search…] [Clear] [Public|Scientist] [view]│
├────────────────────────────┬──────────────────────────────────┤
│ .workspace-pane-left       │ .workspace-pane-right             │
│  (sticky)                  │   #workspace-panel                │
│  .atlas-hero               │   ├ header: eyebrow/title/subtitle│
│   ├ ATC rail (14 buttons)  │   │   + scroll tools (↑ slider ↓) │
│   ├ .atlas-body-wrap (SVG) │   ├ #workspace-scroll-area        │
│   └ region label/preview   │   │   ├ #disease-view-section(D3) │
│                            │   │   └ #drug-grid (cards)        │
│                            │   ├ .workspace-panel-footer       │
│                            │   │   └ .disease-panel            │
│                            │   └ #drug-detail-page (anchored)  │
└────────────────────────────┴──────────────────────────────────┘
```

Key DOM landmarks (in `index.html`):
- `#workspace-panel` — the right pane container; the detail page is positioned relative to it.
- `#workspace-scroll-area` — the scroll container the side wheel/slider drives.
- `#workspace-eyebrow / #workspace-title / #workspace-subtitle` — context header updated by `updateWorkspaceContext()`.
- `#workspace-scroll-up / -slider / -down` — custom scroll controls synced by `syncWorkspaceScrollControls()`.
- `#drug-grid` — the card grid.
- `#disease-view-section` — D3 disease tree (shown in disease view mode).
- `#drug-detail-page` — the **anchored detail surface** (replaces the old full-screen modal).
- `#modal-overlay` (index.html:347) — **legacy modal, now vestigial**; slated for removal once the detail page fully supersedes it.

**Script load order** (from `index.html`): `style.css` → D3 (CDN) → `structure.js` → `stores/graphStore.js` → `stores/selectionStore.js` → `views/genealogyView.js` → `views/diseaseView.js` → data embeds → `assets/human-body-svg.js` → `app-state.js` → `components/disease-panel.js` → `app.js`.

---

## 3. Module Map

| File | Lines | Role |
|------|------:|------|
| `js/app.js` | ~2,760* | `DrugTreeApp` — boot, data loading, routing, filtering, rendering, detail surface. The orchestrator / god object. |
| `js/app-state.js` | ~361 | `DrugTreeState` — **stateless** utilities: `buildDrugIndexes`, `selectDrugIds`, label/summary builders, `getModePresentation`, toggles, `ATC_TO_BODY_REGIONS`. |
| `js/stores/graphStore.js` | ~423 | Drug/disease/region topology (families, edges, nodes, hierarchy); lineage fetch + cache. |
| `js/stores/selectionStore.js` | ~130 | `EventTarget` pub/sub for selection IDs + view mode. Single source of truth for *what is selected*. |
| `js/views/diseaseView.js` | ~825 | D3 body→disease→drug tree; pruning of childless branches; resize handling. |
| `js/views/genealogyView.js` | ~542 | D3 zoomable lineage tree with zoom controls; edge colored by type. |
| `js/components/disease-panel.js` | ~311 | Disease search/select + orphan-only toggle (footer of right pane). |
| `js/components/approval-chips.js` | ~262 | FDA approval status badges. |
| `js/components/mechanism-card.js` | ~247 | Mechanism-of-action card (scientist detail). |
| `js/components/orphan-badge.js` | ~301 | Orphan/rare indication badges. |
| `js/structure.js` | ~304 | `StructureViewer` — RDKit.js SMILES→2D SVG with LRU cache + IntersectionObserver lazy render. |

\* `app.js` grew ~324 lines in the working-tree refactor (orphan filtering, workspace context, scroll controls, anchored overlay positioning).

---

## 4. State Model (summary)

Full inventory: [frontend-state-model.md](./ui/frontend-state-model.md). The essentials:

**Three sources of truth:**
- **`SelectionStore`** owns selection *IDs* (drug, disease, region) and `viewMode`, and emits events: `drug:selected`, `disease:selected`, `region:selected`, `selection:cleared`, `view:changed`.
- **`DrugTreeApp`** owns the *full objects* and derived results: `drugs`, `drugShellsById`, `fullDrugRecordsById`, `diseases`, `diseaseDrugEdges`, `diseaseDrugIdsByDiseaseId`, `orphanDrugIds` (new), `bodyOntology`, `drugIndexes`, and the active filter state (`activeCategory`, `activeBodyRegion`, `activeDisease`, `searchQuery`, `mode`, `viewMode`).
- **`GraphStore`** owns graph topology.

**Data flow is unidirectional:** UI event → `SelectionStore.set*()` → event → `DrugTreeApp.handle*()` → state update → render. Some full objects are intentionally mirrored (ID in the store, object in the app) to avoid repeated lookups; the store ID is authoritative.

**Filter composition** flows through `getVisibleDrugIdsForSelection()` → `selectDrugIds(drugIndexes, {...})` → `applySpecialDrugFilters()` (orphan-only). The four filter dimensions are: ATC category → body region → disease (explicit edge lookup) → text search, plus the orphan-only refinement.

---

## 5. Render Pipeline & Boundaries

`applyFilters()` is the central render orchestrator. The codebase already has a documented **render-boundary map** (`ui/frontend-state-model.md` §7) identifying 10 surfaces (B1 Drug Grid, B2 Body Map, B3 ATC Tags, B4 Filter Chips, B5 Region Label, B6 Detail/Modal, B7 Disease Panel, B8 Disease View, B9 Genealogy, B10 View Toggle). The high-value problems it flags are still live:

- **B1 Drug Grid** rebuilds the whole grid (`innerHTML`) on every filter keystroke, recreating up to ~120 cards including RDKit render scheduling.
- **B2 Body Map** is coupled into `applyFilters()`, recomputing per-region drug counts (14 × O(n)) on *every* search keystroke even though search doesn't change the body map.
- **B8 Disease View** does a full D3 SVG rebuild on region/disease changes even when the region is unchanged.
- **Duplicate cascades:** `clearFilters()` and `handleSelectionCleared()` double-fire several boundaries; `handleRegionSelected()` runs the body map update twice.

These are the backbone of the "optimize the UI rendering" track — see §9.

---

## 6. Data Loading Strategy

Startup is tuned around payload size (embeds total ~9 MB of JS):

1. **Shell first (eager):** `drugs-shell.js` (3.3 MB) gives every drug a light record (id, name, smiles, atc, phase, generation, class, target preview, body regions, search_text) → enough to render cards and filter immediately.
2. **Full records (lazy):** `ensureFullDrugEmbedLoaded()` injects `drugs.js` (4.3 MB) as a `<script>` only when full detail is needed; the API (`/api/v1/drugs`) is tried first.
3. **Graph (deferred):** `scheduleGraphLoad()` loads `graph-nodes.js` (1.1 MB) after first paint.
4. **Structures (on-scroll):** `StructureViewer` renders SMILES→SVG only for cards entering the viewport, max 2 concurrent, LRU-cached (~400 SVGs).

This shell + lazy-hydration + deferred-graph split is deliberate and should be preserved; optimizations should reduce payloads further (compression, code-split, trimming shell fields), not collapse the tiers.

---

## 7. Detail Surface (current refactor)

The drug detail view is migrating from a **full-screen modal** to an **anchored in-panel page** (`#drug-detail-page`):
- `resolveDrugAnchorRect()` captures the clicked card's rect; `positionDrugDetailOverlay()` positions the detail shell relative to `#workspace-panel` with a gutter, so detail opens *in context* rather than as a blocking overlay.
- `lastDetailAnchorRect` + `boundDetailOverlayPositioner` keep it positioned across scroll/resize.
- Routing is still hash-based: `#drug/{id}` via `parseDrugDetailHash()` / `handleHashChange()`, with back-button restore via `lastNonDetailHash`.

**Consequence for docs/code:** the modal-centric descriptions in older docs (and the lingering `#modal-overlay` element) are legacy. New work should target `#drug-detail-page`. Removing the dead modal path is a cleanup item.

---

## 8. Public vs Scientist Mode

A single dataset, gated by `getModePresentation(mode)` and `body.mode-public`/`mode-scientist` classes (`.scientist-only` is CSS-driven). Per `product/project-plan.md`:
- **Public:** name, synonyms, indication, ATC label, body location, brief summary, approval year, small structure thumbnail.
- **Scientist:** the above plus SMILES/InChIKey, descriptors (MW, cLogP, TPSA, HBA/HBD), targets, mechanism, lineage/genealogy, provenance.

The prior audit flagged that cards/detail were not yet *meaningfully* different between modes (e.g., SMILES showing in public). Deepening the mode split is an open product/UI task.

---

## 9. Known Constraints & Optimization Seams (Frontend)

Ranked by leverage. Entry points for the "optimize the UI" track.

| # | Issue | Where | Impact | Direction |
|---|-------|-------|--------|-----------|
| U1 | **Body map recomputed on every keystroke** | `applyFilters()` → `updateBodyMapState()` (B2) | 14×O(n) filter passes per keystroke | Decouple B2; only recompute on category/region change; cache region counts |
| U2 | **Full grid rebuild per filter change** | `renderDrugList()` (B1) | Destroys/recreates ~120 cards + RDKit scheduling | Incremental card diffing; debounce search; mode switch = class toggle, not rebuild |
| U3 | **No virtual scrolling** | `#drug-grid` | DOM bloat on large result sets | Windowed rendering / virtualized grid |
| U4 | **Duplicate render cascades** | `clearFilters()`/`handleSelectionCleared()`, `handleRegionSelected()` | Several boundaries fire twice | Route all downstream updates through the `selection:cleared` handler only |
| U5 | **Full D3 rebuild on unchanged region** | `diseaseView.render()` (B8) | Expensive SVG rebuilds | Diff `currentRegionId`/`currentDiseaseId`; skip if unchanged |
| U6 | **~9 MB embed payload** | `src/frontend/data/*.js` | Slow cold load on weak networks | Gzip/Brotli static serving, trim shell fields, split graph further |
| U7 | **Accessibility gaps** | shell + detail page + D3 trees | No focus trap on detail, sparse aria, no keyboard nav, D3 trees not in a11y tree | Add `aria-modal`/focus management to detail page, `role`/`aria-live` on grid/counts, keyboard nav |
| U8 | **Mobile/touch immaturity** | atlas hover previews, detail anchoring, scroll tools | Hover-only previews and desktop-anchored detail don't translate to touch | Touch-equivalent interactions; responsive detail placement |
| U9 | **`app.js` god object (~2,760 ln)** | `js/app.js` | Hard to test/change | Extract per the seams in `ui/frontend-state-model.md` §8 (DataLoader → DrugGridRenderer → PreviewController → FilterController → AtlasController → DetailController) |
| U10 | **Dead/legacy code** | `#modal-overlay`, any `body-map.js` remnants | Confusion, drift | Remove once detail-page migration lands |

---

## 10. How To Extend (Recipes)

- **Add a card field:** ensure it's in the shell embed (or hydrate from full record), render it in `createDrugCard()`, gate with `.scientist-only` if expert-only.
- **Add a filter dimension:** extend `buildDrugIndexes()` + `selectDrugIds()` in `app-state.js`, thread through `getVisibleDrugIdsForSelection()`, add the UI control + a filter chip.
- **Add a selection-driven view:** subscribe in `initStores()` to the relevant `SelectionStore` event; keep the store as the source of truth for the ID.
- **Touch styling:** use the CSS variables in `style.css` (`--bg-*`, `--text-*`, `--accent-*`, `--atc-*`, spacing/radius scales). Don't hardcode new ATC colors — extend the palette variables.
- **Never** hand-edit `src/frontend/data/*.js` — regenerate from `data/` via `scripts/build_frontend_embeds.py`.

---

## 11. Styling System

`css/style.css` (~2,635 ln, +550 in refactor) is a dark "atlas" theme with glassmorphism, organized by CSS custom properties:
- Palette: `--bg-base/surface/card/elevated`, `--text-primary/secondary/muted`, `--accent-primary/secondary/glow`, 14 `--atc-*` hues.
- Scales: spacing (xs→2xl), radius (sm→full). Fonts: Fraunces (display), IBM Plex Sans (body), JetBrains Mono (code).
- Responsive breakpoints at 1000px / 800px / 600px; mobile is functional but not yet first-class (see U8).
- Glass surfaces: `.topbar`, `.atc-tag`, cards use `backdrop-filter` + translucent backgrounds.

---

## 12. Reference Docs

- `src/frontend/AGENTS.md`, `src/frontend/js/AGENTS.md` — quick module pointers
- `docs/ui/frontend-state-model.md` — exhaustive state + render-boundary + extraction-seam inventory
- `docs/ui/central-body-atlas-implementation.md` — atlas design
- `docs/audits/current-implementation-audit.md` — gap audit (2026-03-13; partially superseded — health-count and detail-surface items have since changed)
- `docs/product/project-plan.md` — product intent, mode/ontology decisions
