# DrugTree — Next Round Plan (UI + Backend Optimization)

**Date:** 2026-06-12 · **Updated:** 2026-06-18 · **Branch:** `optimize-ui-backend-docs-20260613` · **Base commit:** `34933f0`
**Goal of this round:** Land the in-progress two-pane refactor cleanly, then take the highest-leverage UI and backend optimizations in parallel without breaking the JSON-first / embed-fallback / no-build-step invariants.
**Inputs:** [2026-06-12-review-qa.md](./2026-06-12-review-qa.md) (findings), [../Architecture.md](../Architecture.md), [../UI-Architecture.md](../UI-Architecture.md).

Issue IDs below reference the optimization tables in the architecture docs (`U#` = UI-Architecture §9, `B#` = Architecture §6).

## Implementation status (2026-06-13)

Implemented in the current working tree:
- Phase 0 detail-page stabilization: anchored detail scroll positioning, hash route behavior, legacy `#modal-overlay` removal, and core Playwright regression coverage.
- Phase 1 Track A: search no longer recomputes body-map state, region counts are cached, search is debounced, mode switch preserves card DOM, `DrugGridRenderer` performs windowed/virtualized rendering, duplicate clear/region cascades are narrowed, and disease view uses a highlight-only path for unchanged signatures.
- Phase 1 Track B: admin refresh hook, startup cache warm, graph source mtime/size auto-refresh, graph-query source-version cache invalidation, target SQLite work moved to `run_in_threadpool()`, target detail compound query path, bounded list/search endpoints, and explicit disease-tree pagination.
- Phase 2: `drugs.js` and graph bundles removed from eager script payload, generated gzip/Brotli sidecars, compression-aware static test server, detail/grid/D3 a11y basics, Public mode raw-SMILES fallback removal, Scientist lineage provenance from graph-edge embeds, approval/mechanism/orphan component loading, responsive mobile detail/topbar fixes, touch dwell previews, and five ETL files migrated from sync `requests` to `httpx`.
- Phase 3 extractions: `js/data-loader.js`, `js/components/drug-grid-renderer.js`, `js/controllers/{preview,filter,atlas,detail}-controller.js`, `src/backend/etl/{atc_lookup_service,atc_enrichment_pipeline,atc_enrichment_models,atc_enrichment_reports,drug_metadata,drug_transform_helpers,disease_etl_helpers,disease_source_loaders}.py`, and `src/backend/services/{validation_pipeline_core,validation_models}.py`.

Committed locally on branch `optimize-ui-backend-docs-20260613`. The real default full-source `run_etl.sh` path still stops before writes because the required default input `data/processed/compound_master_table.tsv` is missing from this checkout. A separate isolated timed smoke in `/tmp` used a temporary canonical-derived compatibility table and completed the launcher sequence with `ETL_CORE_TIMEOUT_SECONDS=120`, `ETL_STEP_TIMEOUT_SECONDS=5`, `--no-kegg`, and `--limit 20`. Broader axe/manual accessibility review was not run.

---

## 0. Guardrails (do not regress)

- JSON stays canonical at runtime; embeds stay generated (rebuild via `scripts/build_frontend_embeds.py`).
- Frontend remains usable with no backend (API-first, embed fallback).
- No framework, no build step (frontend); no app factory (backend).
- Keep `#drug/{id}` hash routing + browser-back; keep the 1200 ms hover-dwell preview; keep Public/Scientist as one dataset, two views.
- Run gates before declaring done: `pytest tests/backend/` and `npx playwright test --config tests/frontend/playwright.config.ts`.

---

## Phase 0 — Stabilize the refactor (do first, blocks the rest)

The two-pane workspace + anchored detail page began as the unstable surface for this round; it is now stabilized and committed locally on the working branch.

| Task | Detail | Acceptance |
|------|--------|-----------|
| P0.1 Finish anchored detail page | Verify `positionDrugDetailOverlay()` / `resolveDrugAnchorRect()` reposition correctly on scroll, resize, and back-nav; confirm `#drug/{id}` routing + back button restore filters | Open/close/deep-link a drug detail with no layout jump; Playwright p0-regression green |
| P0.2 Remove the dead modal | Delete `#modal-overlay` and any modal-only CSS/JS once the page covers all cases | Implemented: no `#modal-overlay` DOM; method names still carry legacy modal wording |
| P0.3 Wire scroll controls fully | Confirm `syncWorkspaceScrollControls()` fires on scroll/resize/filter; slider + ↑/↓ disabled when nothing to scroll | Controls track scroll position; disabled state correct on short lists |
| P0.4 Verify orphan-only path | `orphanDrugIds` populated at load; `applySpecialDrugFilters()` interacts correctly with disease + category filters | Orphan toggle yields correct counts in both views |
| P0.5 Commit the refactor | Branch, commit with a clear message, keep `Architecture.md`/`UI-Architecture.md` in sync | **Done locally:** branch `optimize-ui-backend-docs-20260613`, commit `11848fc`; not pushed |

---

## Phase 1 — High-leverage performance (UI + backend in parallel)

### Track A — Frontend rendering (U1, U2, U4, U5)

| Task | Detail | Acceptance |
|------|--------|-----------|
| A1 Decouple body map from `applyFilters()` (U1) | Only recompute region drug-counts when `activeCategory`/`activeBodyRegion` changes, not on search keystroke; cache counts, invalidate on data/index rebuild | **Done:** cached count helper + search `updateBodyMap: false`; Playwright regression green |
| A2 Debounce + incremental/virtual grid (U2/U3) | Search input uses a short 40 ms debounce; mode switch preserves card DOM; large result sets render through a bounded card window | **Done:** `DrugGridRenderer` virtualizes large visible sets and smoke tests assert bounded DOM card count |
| A3 De-duplicate cascades (U4) | Route clear-path updates through `handleSelectionCleared()` when `SelectionStore` has active selection; remove redundant region body-map update | **Done:** p0 regression asserts one region body-map update and clear-store path |
| A4 Diff disease D3 tree (U5) | Skip D3 update/rebuild when `currentRegionId`/`currentDiseaseId` signature is unchanged; update node highlight only | **Done:** p0 regression asserts root stability, zero `update()` calls, one highlight update |

### Track B — Backend correctness & latency (B1, B2, B3, B4, B5)

| Task | Detail | Acceptance |
|------|--------|-----------|
| B1 Fix graph-index staleness | Add mtime/source-hash check to `graph_index.py`; include graph source version in query-cache key; keep `/api/v1/admin/refresh`; warm the index at startup | **Done:** focused backend tests cover fallback/artifact source refresh and query cache versioning |
| B2 Async/threadpool targets DB | Move `routers/targets.py` off per-request sync `sqlite3` to the async pool in `db/connection.py` (or `run_in_threadpool`) | **Done:** blocking target SQLite work runs behind `run_in_threadpool()`; targets endpoints unchanged externally |
| B3 Collapse target N+1 | Replace the 3 SELECTs in `GET /targets/{id}` with JOINs/batched query | **Done:** regression test asserts one compound execute path and identical response shape |
| B4 Bound the open endpoints | Add `limit`/`offset` (+ caps) to `/drugs/search`, `/drugs/category/{c}`, `/diseases/search/{q}`, `/diseases/region/{r}`, `/diseases/{id}/drugs` | **Done:** reviewed list endpoints are paginated/capped; target-drug pagination regression added |
| B5 Replace `[:20]` slice | Give `/tree/disease/{id}` real pagination + a documented cap | **Done:** explicit disease-tree pagination is in place |

---

## Phase 2 — Payload, polish, and accessibility

| Task | Detail | Acceptance |
|------|--------|-----------|
| C1 Shrink embed payload (U6) | Serve embeds gzip/Brotli on the static path; lazy-load graph bundles only when graph features are used | **Done:** generated sidecars, compression-aware server, Playwright compression assertion |
| C2 Detail-page a11y (U7) | Focus trap + focus restore on `#drug-detail-page`; `aria-modal`, labelled-by; `aria-live` on drug count; keyboard close/nav | **Done for automated scope:** Playwright covers detail semantics, focusable controls, and mobile placement; axe/manual screen-reader scan not run |
| C3 Grid + D3 a11y semantics (U7) | `role`/`aria` on `#drug-grid`, cards, atlas regions, controls, and D3 tree nodes; ensure keyboard activation | **Done for core paths:** cards, atlas regions, toggles, and D3 nodes are keyboard/ARIA-covered; broader screen-reader QA still recommended |
| C4 Deepen Public/Scientist split (UI §8) | Hide SMILES/InChIKey/descriptors in Public; reveal available chemistry/lineage/provenance in Scientist | **Done for available data:** raw SMILES hidden in Public; Scientist shows current canonical expert fields plus lineage confidence/provenance from generated graph-edge embeds. cLogP/TPSA/HBA/HBD are not in canonical data, so they are not displayed |
| C5 ETL async migration (B6) | Migrate the 5 sync-`requests` ETL files to `httpx` with try/except + graceful degradation | **Done for code/test/smoke scope:** no sync `requests`, direct `httpx.get/post`, `time.sleep`, or `ThreadPoolExecutor` in those files; `run_etl.sh` now wraps required and optional steps with configurable timeouts; isolated timed smoke completed. Real default source-table ETL remains unproven until `data/processed/compound_master_table.tsv` is supplied |

---

## Phase 3 — Structural (optional / as capacity allows)

| Task | Detail | Acceptance |
|------|--------|-----------|
| D1 Extract from `app.js` (U9) | Follow `docs/ui/frontend-state-model.md` §8 order: DataLoader → DrugGridRenderer → PreviewController → FilterController → AtlasController → DetailController; keep each behind the same DOM contract | **Done for planned seams:** all listed modules/controllers exist; `app.js` is now an orchestration shell with compatibility wrappers |
| D2 Touch/mobile pass (U8) | Touch-equivalent for hover previews; responsive detail-page placement; verify atlas SVG interaction on touch | **Done for core flows:** touch dwell previews and mobile detail/topbar overflow verified by Playwright visual snapshot |
| D3 Split large backend modules (B7) | Break up `atc_orchestrator`, `drug_etl`, `disease_etl`, `validation_pipeline` by stage; add focused unit tests | **Done for named files:** split modules are under ~600 lines; backend focused and full suites passed |

---

## Sequencing & rationale

1. **Phase 0 is a hard prerequisite** — a half-migrated detail surface plus a vestigial modal is a correctness landmine. The detail surface and docs are now synchronized in the working tree; commit/push is still outside this plan update.
2. **Phase 1 runs two tracks in parallel.** Track A (U1 especially) is the cheapest, most visible UI win — kill the per-keystroke 14×O(n) body-map recompute first. Track B1 (graph staleness) is the most important *correctness* fix on the backend; B2/B3 are the latency fixes.
3. **Phase 2** is breadth: payload, accessibility, the Public/Scientist depth the product spec calls for, and ETL hygiene.
4. **Phase 3** is structural debt — valuable but lower urgency; do it when it unblocks the above rather than for its own sake.

## Definition of done (per task)
- Behavior verified in the running app (not just unit tests) for UI tasks; `pytest tests/backend/` for backend tasks.
- Playwright p0-regression green; visual snapshots captured by `tests/frontend/e2e/visual-snapshots.spec.ts`; no new console errors in file-launch probe.
- Architecture docs updated if the change alters a documented contract or seam.
- For data-shape changes: embeds regenerated and the backend graph singleton refreshed/restarted.

## Verification evidence (2026-06-13)
- `pytest tests/backend/` — 327 passed, 8 warnings.
- `npx playwright test --config tests/frontend/playwright.config.ts --reporter=line` — final rerun 73 passed.
- `npx playwright test --config tests/frontend/playwright.config.ts --reporter=line tests/frontend/e2e/visual-snapshots.spec.ts` — 1 passed; regenerated `.sisyphus/evidence/visual-snapshots/*.png`, including an inspected Scientist detail snapshot showing atorvastatin lineage provenance without detail-page auto-scroll clipping.
- `npx playwright test --config tests/frontend/playwright.config.ts --reporter=line tests/frontend/e2e/genealogy.spec.ts` — 13 passed.
- `node tests/frontend/test_file_safe_bootstrap.mjs` — 5 passed, including generated graph-edge lineage evidence retention.
- `node tests/frontend/e2e/disease-universe.mjs` — 19 passed.
- `node tests/frontend/test_disease_interactions.mjs` — 9 passed.
- `node tests/frontend/test_disease_wiring.mjs` — 8 passed.
- Latest frontend perf evidence: cold boot median `1131.6 ms` / budget `1800 ms`; filter interaction median `112.6 ms` / budget `120 ms`; route-to-detail median `485.7 ms` / budget `500 ms`.
- Focused backend ETL/router suites passed before the full backend run.
- `bash -n src/backend/run_etl.sh` — passed.
- `pytest tests/backend/test_drug_etl.py tests/backend/test_etl_httpx_migration.py tests/backend/test_database_update_contract.py` — 19 passed.
- `timeout 60s bash src/backend/run_etl.sh` in the real checkout — failed before writes: missing `data/processed/compound_master_table.tsv`.
- `ETL_CORE_TIMEOUT_SECONDS=120 ETL_STEP_TIMEOUT_SECONDS=5 timeout 240s bash src/backend/run_etl.sh --no-kegg --limit 20` in an isolated `/tmp` copy with a temporary canonical-derived `COMPOUND_MASTER_TABLE` — completed: `Transformed 20 drugs, skipped 0`, optional source fetches degraded with warnings/timeouts, graph/frontend artifacts rebuilt, and SQLite loading finished.
- `git check-ignore` returned no ignore match for `docs/Architecture.md`, `docs/UI-Architecture.md`, `docs/modules/README.md`, or the current plan/Q&A files.
- Implementation commits before this documentation alignment include `11848fc refactor: optimize drugtree ui and backend modules`, `838bb76 docs: record optimization verification status`, `4764bc3 docs: clear stale plan wording`, and `ce1e1eb fix: drug ETL transform helpers and test contract updates` on `optimize-ui-backend-docs-20260613`.

## Phase 4 — Browser review follow-ups (2026-06-18, docs only)

**Review method:** Live browser pass on `http://127.0.0.1:8080` (embed-only, no backend). Viewports tested: 1440, 1200, 1000, 800, 390. No code changes in this pass — findings recorded for the next implementation round.

### Track E — Responsive / auto-fit layout (user priority #1)

| Task | Detail | Acceptance |
|------|--------|-----------|
| E1 Fluid workspace grid | Replace fixed `grid-template-columns: minmax(620px, 0.98fr) minmax(720px, 1.18fr)` with fluid `fr` columns and a single intermediate breakpoint band (≈1000–1340px currently overflows horizontally). | No horizontal scroll at 1200px; both panes visible without clipping |
| E2 Container-driven D3 sizing | `DiseaseView` defaults to 1120px width with 220px left/right margins; in a ~580px right pane this leaves ~140px for tree content — graph looks empty. ResizeObserver exists but margins/spacing must scale with container width. | Disease tree readable at all desktop widths; nodes not clustered into a single dot |
| E3 Collapse atlas hero on narrow viewports | Hero copy + summary pills consume ~250px vertical space before the body SVG; on mobile (390px) the body appears below ~980px scroll offset. Add compact/collapsible hero or body-first mobile layout. | Body atlas visible within first screen on phone |
| E4 Vertical scroll budget | At 390px stacked layout, right workspace panel height exceeds 27,000px (virtualized grid + long drug list). Add sticky section tabs or collapse secondary panels (Disease Focus below grid) on mobile. | Mobile scroll height proportional to visible cards, not full dataset |
| E5 Topbar density | Four toggle groups (Clear, Genealogy/Disease, Public/Scientist) wrap awkwardly between 600–1000px. Consider icon-only mode or overflow menu. | Topbar usable without wrapping past two rows at 800px |

### Track F — Light theme (user priority #2)

| Task | Detail | Acceptance |
|------|--------|-----------|
| F1 Theme token split | `style.css` is dark-only (`--bg-base: #0f172a`, etc.). Introduce `[data-theme="light"]` / `[data-theme="dark"]` token sets; no hardcoded colors outside tokens. | Both themes render all surfaces (atlas, cards, detail, D3) |
| F2 Theme toggle + persistence | No theme toggle exists today. Add topbar control; persist choice in `localStorage`; optional `prefers-color-scheme` default on first visit. | Toggle works; survives reload; respects OS preference when unset |
| F3 SVG / RDKit / D3 contrast | Body atlas glow, region fills, disease-tree nodes, and RDKit structure canvas need light-theme variants (drop-shadows, stroke contrast, white structure background already OK). | WCAG AA contrast on primary text and interactive regions in light mode |
| F4 Visual snapshot update | Regenerate Playwright visual snapshots for both themes. | `visual-snapshots.spec.ts` green for dark + light |

### Track G — Visual redesign / body atlas layout (user priority #3)

| Task | Detail | Acceptance |
|------|--------|-----------|
| G1 Body-first atlas composition | Current layout: hero headline → summary pills → 3-column constellation (ATC rails + 344px body). Body feels small relative to marketing copy. Prototype: body-dominant center stage with ATC as orbit/chip ring or bottom strip; collapsible hero. | Body SVG is the visual anchor; ATC discoverable without side-rail truncation |
| G2 ATC rail legibility | Right-rail labels truncate ("Respirat…", "Anti-infe…", "GU/E…") in the left pane at moderate widths. Widen rail budget, allow two-line labels, or move to wrapped chip grid (partially done at ≤1000px). | Full ATC names readable without hover |
| G3 Information hierarchy in workspace | Right panel repeats "Matching Drugs" / "Disease Hierarchy" headings; Disease Focus competes with grid for space. Consider tabbed workspace (Drugs / Diseases / Detail) or split-pane with resizable divider. | Clear primary action per view mode; less duplicated chrome |
| G4 Empty-state polish | Disease graph panel looks empty until region + disease selected; collapsed tree nodes are nearly invisible. Add skeleton/placeholder illustration and onboarding hint. | First-time user sees what to click within 3 seconds |
| G5 Design system pass | Unify spacing scale, reduce nested gradient borders (`workspace-panel::before`, `atlas-stage::before`), tighten Fraunces display + IBM Plex pairing, soften neon glow for a cleaner clinical aesthetic. | Coherent visual language across atlas, cards, detail, graphs |

### Track H — Backend data agent supervision (user request)

| Task | Detail | Acceptance |
|------|--------|-----------|
| H1 Approval year enrichment | **100%** of drugs lack `year_approved` (UI shows "Unknown" everywhere, e.g. Lisinopril). Agent pipeline: FDA Orange Book / openFDA / EMA EPAR crosswalk by name/InChIKey. | ≥70% of Phase IV drugs have a sourced approval year with provenance tag |
| H2 ATC placeholder resolution | **42.6%** (3,133/7,359) drugs carry placeholder `*99XX99` ATC codes. Extend existing ChEMBL/KEGG/PubChem ETL with agent-supervised disambiguation for remaining gaps. | Placeholder rate <10%; changes logged in `data/changes/` |
| H3 Disease–drug edge expansion | Only **64 edges** linking **36 unique drugs** to 50 diseases (~1.3 edges/disease). Disease view is sparse beyond demo hypertension cluster. Agent: correlate DrugBank/CTD/DisGeNET/openFDA indications → `disease_drug_edges.json`. | ≥5× edge coverage; each disease has ≥1 sourced edge or explicit "no approved drug" flag |
| H4 Company / sponsor validation | Only **12.8%** have `company` populated; Lisinopril shows "Azurity Pharmaceuticals" (likely incorrect for originator). Agent-verify sponsor vs. generic/API entry. | Company field has source URL; obvious mismatches flagged in audit report |
| H5 Target / class completeness | **55.7%** have targets; drug class often null in Public cards. Correlate with ChEMBL mechanism of action, UniProt, Pharos. | Scientist cards show class + targets for ≥80% of small-molecule entries |
| H6 Agent audit loop | New ETL stage: `agent_data_supervisor.py` — batch records, web evidence fetch (with try/except + rate limits), confidence score, human-review queue in `data/reports/`. | Report per run; no silent overwrite of high-confidence existing values |

### Sequencing (Phase 4)

1. **E1 + E2** — fix layout breakage and invisible disease graph (highest user-visible correctness).
2. **G1 + G2** — body atlas redesign (explicit user ask).
3. **F1 + F2** — light theme (moderate effort, high user ask).
4. **H1 + H2 + H3** — data supervision (parallel backend track; unblocks richer UI).
5. **G3–G5, E3–E5, F3–F4, H4–H6** — polish and breadth.

### Browser verification evidence (2026-06-18)

- App loads cleanly at 1440px; cold `DOMContentLoaded` ≈ 303 ms (embed-only).
- **1200px:** two-pane grid overflows (`620px + 720px` > viewport); right pane clipped.
- **1000px:** stacks to single column; ATC rails become wrapped chips (good); body SVG not visible without scroll.
- **800px / 390px:** atlas hero + ATC grid dominate first screen; body appears far below fold; right workspace stacks underneath with extreme vertical scroll.
- **Disease view:** selecting Heart/Vascular → Hypertension shows tree in a11y tree but graph is visually near-empty; SVG width 580px with 220px margins each side.
- **Drug detail:** `#drug/lisinopril` renders structure + metadata; Scientist mode adds class/MW/InChIKey/SMILES; `year_approved` = Unknown.
- **Theme:** dark only; `getComputedStyle(body).backgroundColor` = `rgb(15, 23, 42)`; no theme toggle in DOM.
- **Console:** no JS errors observed during review.

---

## Phase 4 — Implementation status (2026-06-18)

All four Phase 4 tracks were implemented this round and verified with visual snapshots + the full automated suite. Method: implement → capture Playwright visual snapshots → inspect the PNGs (not just green assertions) → fix what the images/tests revealed → re-verify.

### Track E — Responsive / auto-fit layout — **Done**
- **E1** fluid shell grid `minmax(0, 0.94fr) minmax(0, 1.06fr)` (no 620/720 floor); no horizontal overflow at 1440/1200/1000/800/390 (asserted).
- **E2** D3 disease/genealogy margins + depth spacing now scale with container width; disease-tree height is content-driven (removed the `Math.max(measuredHeight, …)` force and the CSS `min-height: 640/760px` floors) so sparse regions render compactly instead of as a near-empty box.
- **E3** compact, collapsible atlas hero (`#atlas-collapse-toggle`), auto-collapsed ≤860px; body-first mobile layout (body within first screen, asserted `bodyVisibleTop < viewport`).
- **E4** mobile `#workspace-panel` bounded height → virtualized grid scrolls internally; page height dropped from ~27,000px to `< 6000px` (asserted).
- **E5** topbar fits without wrapping past two rows at 800px (incl. the new theme toggle).

### Track G — Visual redesign / body atlas — **Done**
- **G1** body-dominant atlas: compact hero, body SVG fills the core (`flex: 1`, height-driven), ATC as a wrapping `.atc-strip`.
- **G2** ATC legibility: chips show full names with a colored code badge + high-contrast name; no more truncated side-rail labels.
- **G3** information hierarchy: removed the duplicate static "Matching Drugs" `<h2>` (the dynamic `#workspace-title` is the single section heading); trimmed verbose subtitles.
- **G4** disease empty-state placeholder (icon + message + onboarding hint) instead of bare text.
- **G5** design pass: softened glow/drop-shadows, tightened display type sizes, lighter chrome.
- Note: disease-graph *richness* (density of nodes) is still gated on **H3** data (edge coverage), not layout — the layout bug is fixed.

### Track F — Light theme — **Done**
- **F1** `:root` dark token set + `[data-theme="light"]` overrides (tokens + bespoke gradient surfaces: atlas stage, workspace panel + chrome, chips, body-SVG fills, detail surface, scrim).
- **F2** `#theme-toggle` flips + persists `localStorage['drugtree-theme']`; inline `<head>` script applies theme before first paint with priority saved → `prefers-color-scheme` → dark. Playwright pins `colorScheme: 'dark'` so dark stays the canonical default under test.
- **F3** light contrast for text, body SVG, D3 node labels, and the detail surface (previously a hardcoded dark gradient).
- **F4** light-theme snapshots captured (`light-home/search/disease/detail`) alongside the dark canonical set.

### Track H — Backend data agent supervision — **Pipeline done; full coverage is a follow-up**
- **H6** `src/backend/etl/agent_data_supervisor.py`: audit loop with pluggable `FieldAdapter`s, per-adapter timeout + capped retries + graceful degradation, provenance tags, **no silent overwrite**, confidence gating, human-review queue (`data/reports/`), change records (`data/changes/`), resumable checkpoints (`data/checkpoints/`). Opt-in `run_etl.sh` step (`AGENT_SUPERVISOR=1`, timeout-wrapped); does not regenerate embeds.
- **H1/H4** openFDA approval-year + company adapters; **H2** ChEMBL ATC-placeholder resolution; **H5** ChEMBL mechanism targets/class; **H3** ChEMBL-indication disease–drug edge builder (demo: 64 → 98 edges, all 50 diseases covered).
- 22 new backend tests (mocked network) cover no-overwrite, provenance, confidence gating, resume, and degradation.
- **Honest coverage:** the bounded demo run resolved only a small fraction of a random sample; the H1/H2/H3 coverage *targets* (≥70% year, <10% placeholder, ≥5× edges) need a full network-bound `--apply` run with InChIKey crosswalk + more sources. Canonical `data/*.json` left untouched this round.

### Verification evidence (2026-06-18)
- `npx playwright test --config tests/frontend/playwright.config.ts` — **81 passed** (incl. canonical `visual-snapshots.spec.ts`, `p0-regression`, `genealogy`, `disease`, perf baselines, and the new `atlas-responsive.spec.ts`).
- Three real regressions from the layout changes were found via the suite and fixed: (1) disease label truncation (drug-label budget widened by the new margins → tightened); (2) region-root click eaten by a child node's left-extended hit area at tight depth spacing → hit-area left offset now clears the parent column; (3) genealogy detail-tree root clipped off a cramped (~197px) column → genealogy margins now scale with container width.
- `node` frontend tests — `test_file_safe_bootstrap.mjs` 5, `test_disease_interactions.mjs` 9, `test_disease_wiring.mjs` 8, `test_app_state.mjs` 5, `disease-universe.mjs` 19, all passing. `test_disease_interactions.mjs` was updated (per "trust the snapshot, not the stale assertion") to expect content-driven disease-view height instead of the removed fixed 640/760px floors.
- `pytest tests/backend/` — **349 passed** (327 prior + 22 new agent-supervisor tests).
- Visual snapshots regenerated under `.sisyphus/evidence/visual-snapshots/` and inspected: `desktop-home`, `desktop-scientist-detail` (lineage provenance intact), `desktop-disease-view`, `mobile-home`, `resp-{1440,1200,1000,800}`, `resp-390`, `resp-disease-1200(-full)`, `light-{home,search,disease,detail}`.

---

---

## Phase 5 — UI polish follow-ups (2026-06-18)

### Changes implemented

| Item | Change | Files |
|------|--------|-------|
| Scroll drift fix | Removed the custom vertical slider/scroll-tools widget (`workspace-scroll-tools`). The native browser scrollbar now owns all scroll position tracking; removed the re-entrant `syncWorkspaceScrollControls` calls that caused the slider to keep moving after a mouse-wheel stop. | `index.html`, `app.js`, `style.css` |
| Remove Disease Focus footer | Removed `#disease-panel` (`workspace-panel-footer`) from the workspace panel. The disease selection state still works via the D3 disease-graph view (Disease mode) and the Active Filters chip. Orphan toggle stays in the header controls. | `index.html`, `app.js`, `style.css` |
| Column picker | Added a `Cols: 2 3 4 5 6 7 8 9` button group (`#grid-cols-picker`) next to Orphan Only. Selection persists via `localStorage`. The chosen count is applied as a CSS custom property (`--grid-cols-template`) on `#drug-grid`, which both the normal and virtualized (`drug-grid-window`) grids inherit. At 5+ cols, card structure preview height shrinks (110 → 80px) and card padding compresses. The virtual renderer's `getGridMetrics` respects `app.gridColumns`. | `index.html`, `app.js`, `drug-grid-renderer.js`, `style.css` |
| Disease hierarchy breathing room | Node vertical spacing increased (disease ×80, drug ×54 px per node, up from 66/44). Node label font adjusted to 14px (was 16px inconsistently applied) and text elements to 13px with `letter-spacing`. | `diseaseView.js`, `style.css` |
| Dev cache-bust | `serve_frontend.py` now sends `Cache-Control: no-cache` for `.html/.css/.js/.json` to prevent stale-asset issues after frontend updates. | `scripts/serve_frontend.py` |

### Verification
- Page loads; scroll tools widget absent; disease focus footer absent.
- Column picker shows 2–9 buttons; "3" active by default; selecting another value rerenders cards with the correct column count and compact card sizing.
- Disease hierarchy nodes are more spread out and legible.
- No JS console errors observed.

---

## Open questions for the maintainer
1. **Hosting target for compression (C1):** local/test static hosting now serves sidecars. For GitHub Pages/CDN, confirm whether precompressed `.br`/`.gz` sidecars are honored or need deployment config.
2. **Backend in production:** is the FastAPI service actually deployed, or is the app effectively embed-only today? This re-ranks Track B vs. Track A.
3. **Detail-page vs modal:** answered for this implementation pass — the anchored in-panel page is treated as the current contract, and `#modal-overlay` was removed.
4. **Schema migration:** stay on the current flat record shape, or move toward the nested `docs/product/project-plan.md` Schema v1? This gates C4's depth.
5. **Light theme default (F2):** should first visit follow OS `prefers-color-scheme`, or default dark with manual opt-in?
6. **Body atlas redesign direction (G1):** prefer keeping the constellation + side rails (scaled up), or a new body-dominant layout with ATC as a bottom chip bar / orbit ring?
7. **Agent supervision scope (H):** which external sources are approved for automated writes (openFDA, ChEMBL, KEGG, DrugBank, LLM-assisted extraction)? Any licensing constraints?
