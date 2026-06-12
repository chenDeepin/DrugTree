# DrugTree UI Architecture

**Status:** Living document · **Last reviewed:** 2026-06-13 (branch `main`, base commit `34933f0`, with current working-tree UI optimization pass)
**Audience:** Anyone optimizing or extending the frontend.
**Companion:** [Architecture.md](./Architecture.md) covers the backend/data layer. For an exhaustive state inventory see [frontend-state-model.md](./ui/frontend-state-model.md).

This document is the frontend map: the shell, the module graph, the state model, the render pipeline, and the seams to optimize. It reflects the **two-pane workspace + anchored detail-page** surface currently in the working tree.

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
- `#drug-detail-page` — the **anchored detail surface**. It is labelled as a dialog, traps focus while open, and restores focus to the opener when closed.

**Script load order** (from `index.html`): `style.css` → D3 (CDN) → `structure.js` → `stores/graphStore.js` → `stores/selectionStore.js` → `views/genealogyView.js` → `views/diseaseView.js` → shell/data embeds (not `drugs.js`, not graph bundles) → `assets/human-body-svg.js` → `app-state.js` → `js/data-loader.js` → `components/approval-chips.js` → `components/mechanism-card.js` → `components/orphan-badge.js` → `components/disease-panel.js` → `components/drug-grid-renderer.js` → `app.js`.

---

## 3. Module Map

| File | Lines | Role |
|------|------:|------|
| `js/app.js` | 2,586 | `DrugTreeApp` — boot, routing, filtering, detail surface, and orchestration around extracted helpers. Still the largest frontend module. |
| `js/data-loader.js` | 62 | Shared data-loading helpers: dataset normalization, full-record merge, lazy script loading, API fetch timeout, and next-paint scheduling. |
| `js/components/drug-grid-renderer.js` | 142 | Incremental drug-grid DOM reconciliation, count/note updates, empty state rendering, and card selection sync. |
| `js/app-state.js` | ~361 | `DrugTreeState` — **stateless** utilities: `buildDrugIndexes`, `selectDrugIds`, label/summary builders, `getModePresentation`, toggles, `ATC_TO_BODY_REGIONS`. |
| `js/stores/graphStore.js` | ~423 | Drug/disease/region topology (families, edges, nodes, hierarchy); lineage fetch + cache. |
| `js/stores/selectionStore.js` | ~130 | `EventTarget` pub/sub for selection IDs + view mode. Single source of truth for *what is selected*. |
| `js/views/diseaseView.js` | 913 | D3 body→disease→drug tree; pruning of childless branches; highlight-only path for unchanged signatures; keyboard-accessible tree nodes; resize handling. |
| `js/views/genealogyView.js` | 570 | D3 zoomable lineage tree with zoom controls, edge colors, tree roles, and keyboard-activatable nodes. |
| `js/components/disease-panel.js` | ~311 | Disease search/select + orphan-only toggle (footer of right pane). |
| `js/components/approval-chips.js` | ~262 | FDA approval status badges. |
| `js/components/mechanism-card.js` | ~247 | Mechanism-of-action card (scientist detail). |
| `js/components/orphan-badge.js` | ~301 | Orphan/rare indication badges. |
| `js/structure.js` | ~304 | `StructureViewer` — RDKit.js SMILES→2D SVG with LRU cache + IntersectionObserver lazy render. |

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

`applyFilters()` is the central render orchestrator. The codebase has a documented **render-boundary map** (`ui/frontend-state-model.md` §7) identifying 10 surfaces (B1 Drug Grid, B2 Body Map, B3 ATC Tags, B4 Filter Chips, B5 Region Label, B6 Detail Page, B7 Disease Panel, B8 Disease View, B9 Genealogy, B10 View Toggle). Several high-value issues have been narrowed in the current pass:

- **B1 Drug Grid** is delegated to `DrugGridRenderer`, which reuses/moves existing `.drug-card` nodes by `data-drug-id` and skips no-op signatures.
- **B2 Body Map** is decoupled from text-search filtering; search no longer recomputes per-region drug counts.
- **B8 Disease View** skips D3 update work when the render signature is unchanged and refreshes node highlight classes only.
- **Duplicate cascades:** `handleRegionSelected()` no longer runs the body map update twice, and `clearFilters()` routes store-backed clears through `handleSelectionCleared()` once.

These are the backbone of the "optimize the UI rendering" track — see §9.

---

## 6. Data Loading Strategy

Startup is tuned around payload size (embeds total ~9 MB of JS):

1. **Shell first (eager):** `drugs-shell.js` (3.3 MB) gives every drug a light record (id, name, smiles, atc, phase, generation, class, target preview, body regions, search_text) → enough to render cards and filter immediately.
2. **Full records (lazy):** `ensureFullDrugEmbedLoaded()` injects `drugs.js` (4.2 MB) as a `<script>` only when full detail is needed or file-based tests need complete data; the API (`/api/v1/drugs`) is tried first.
3. **Graph (lazy/deferred):** `loadGraphData()` injects `graph-meta.js`, `graph-nodes.js`, and `graph-edges.js` with `loadScriptOnce()` only when graph features initialize; those bundles are no longer eager in `index.html`.
4. **Structures (on-scroll):** `StructureViewer` renders SMILES→SVG only for cards entering the viewport, max 2 concurrent, LRU-cached (~400 SVGs).

This shell + lazy-hydration + lazy-graph split is deliberate and should be preserved. Generated `.gz`/`.br` sidecars are written by `scripts/build_frontend_embeds.py` and served by `scripts/serve_frontend.py` in local/test static hosting.

---

## 7. Detail Surface (current refactor)

The drug detail view is an **anchored in-panel page** (`#drug-detail-page`). The implementation still uses some legacy method names (`showDrugModal()`, `closeModal()`), but the DOM surface is the detail page:
- `resolveDrugAnchorRect()` captures the clicked card's rect; `positionDrugDetailOverlay()` positions the detail shell relative to `#workspace-panel` with a gutter, so detail opens *in context* rather than as a blocking overlay.
- `lastDetailAnchorRect` + `boundDetailOverlayPositioner` keep it positioned across scroll/resize.
- Routing is still hash-based: `#drug/{id}` via `parseDrugDetailHash()` / `handleHashChange()`, with back-button restore via `lastNonDetailHash`.
- `#drug-detail-page` has dialog semantics, `aria-labelledby`/`aria-describedby`, focus trapping, and focus restoration.

New work should target `#drug-detail-page`; do not reintroduce `#modal-overlay`.

---

## 8. Public vs Scientist Mode

A single dataset, gated by `getModePresentation(mode)` and `body.mode-public`/`mode-scientist` classes (`.scientist-only` is CSS-driven). Per `product/project-plan.md`:
- **Public:** name, synonyms, indication, ATC label, body location, brief summary, approval year, small structure thumbnail.
- **Scientist:** the above plus SMILES/InChIKey, available descriptors (currently MW in canonical data), targets, mechanism where curated, lineage/genealogy, and provenance when the canonical data adds it.

The current pass removes raw SMILES from public card attributes/fallbacks, keeps expert snippets behind `.scientist-only`, loads the approval/mechanism/orphan component scripts, and renders approval chips on drug cards. Deeper descriptor/provenance disclosure depends on adding those fields to canonical data first.

---

## 9. Known Constraints & Optimization Seams (Frontend)

Ranked by leverage. Entry points for the "optimize the UI" track.

| # | Issue | Where | Impact | Direction |
|---|-------|-------|--------|-----------|
| U1 | **Body map search coupling resolved** | `applyFilters({ updateBodyMap })` | Search no longer triggers 14×O(n) body-map passes | Keep explicit body-map updates for category/region/disease highlight paths |
| U2 | **Incremental grid renderer in place** | `DrugGridRenderer` (B1) | Visible result changes reuse/move existing card nodes instead of broad `innerHTML` replacement | Future: virtualized grid for very large visible sets |
| U3 | **No virtual scrolling** | `#drug-grid` | DOM bloat on large result sets | Windowed rendering / virtualized grid |
| U4 | **Duplicate render cascades narrowed** | `handleRegionSelected()`, `clearFilters()` | Region and clear paths no longer double-render core boundaries | Continue chip-specific diffing later |
| U5 | **Disease highlight-only path in place** | `diseaseView.render()` (B8) | Same signature updates node highlight classes only; filter changes still prune branches | Keep D3 accessibility and resize tests with future edits |
| U6 | **Initial payload + transfer size reduced** | `src/frontend/data/*.js`, `scripts/serve_frontend.py` | `drugs.js` and graph bundles are lazy; generated `.gz`/`.br` sidecars cut transferred bytes | Future: trim shell fields further |
| U7 | **Core + D3 a11y improved** | shell, detail page, D3 views | Detail focus trap/restore, grid/list semantics, live count, keyboard cards, tree roles/keyboard nodes | Future: broader axe pass |
| U8 | **Touch/mobile pass improved** | atlas previews, detail page, topbar | Touch dwell opens previews; mobile detail is fixed within viewport; topbar no longer causes horizontal overflow | Continue full phone-flow UX polish |
| U9 | **`app.js` god object (2,586 ln)** | `js/app.js` | Hard to test/change; `js/data-loader.js` and `DrugGridRenderer` are first extractions | Continue per `ui/frontend-state-model.md` §8 (PreviewController → FilterController → AtlasController → DetailController) |
| U10 | **Legacy modal DOM removed** | `#drug-detail-page` | `#modal-overlay` no longer exists | Keep code/docs on the anchored detail-page contract |

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
