# DrugTree — Next Round Plan (UI + Backend Optimization)

**Date:** 2026-06-12 · **Updated:** 2026-06-13 · **Branch:** `main` · **Base commit:** `34933f0`
**Goal of this round:** Land the in-progress two-pane refactor cleanly, then take the highest-leverage UI and backend optimizations in parallel without breaking the JSON-first / embed-fallback / no-build-step invariants.
**Inputs:** [2026-06-12-review-qa.md](./2026-06-12-review-qa.md) (findings), [../Architecture.md](../Architecture.md), [../UI-Architecture.md](../UI-Architecture.md).

Issue IDs below reference the optimization tables in the architecture docs (`U#` = UI-Architecture §9, `B#` = Architecture §6).

## Implementation status (2026-06-12)

Implemented in the current working tree:
- Phase 0 detail-page stabilization: anchored detail scroll positioning, hash route behavior, legacy `#modal-overlay` removal, and core Playwright regression coverage.
- Phase 1 Track A: search no longer recomputes body-map state, region counts are cached, search is debounced, mode switch preserves card DOM, `DrugGridRenderer` performs keyed/incremental card reconciliation, duplicate clear/region cascades are narrowed, and disease view uses a highlight-only path for unchanged signatures.
- Phase 1 Track B: admin refresh hook, startup cache warm, graph source mtime/size auto-refresh, graph-query source-version cache invalidation, target SQLite work moved to `run_in_threadpool()`, target detail compound query path, bounded list/search endpoints, and explicit disease-tree pagination.
- Phase 2: `drugs.js` and graph bundles removed from eager script payload, generated gzip/Brotli sidecars, compression-aware static test server, detail/grid/D3 a11y basics, Public mode raw-SMILES fallback removal, approval/mechanism/orphan component loading, responsive mobile detail/topbar fixes, touch dwell previews, and five ETL files migrated from sync `requests` to `httpx`.
- Phase 3 first extractions: `js/data-loader.js`, `js/components/drug-grid-renderer.js`, and `src/backend/etl/atc_utils.py`.

Still open: no commit/push has been made; virtualized grid, PreviewController/FilterController/AtlasController/DetailController extractions, larger backend module splits, full ETL run, and broader axe/manual accessibility review remain future work.

---

## 0. Guardrails (do not regress)

- JSON stays canonical at runtime; embeds stay generated (rebuild via `scripts/build_frontend_embeds.py`).
- Frontend remains usable with no backend (API-first, embed fallback).
- No framework, no build step (frontend); no app factory (backend).
- Keep `#drug/{id}` hash routing + browser-back; keep the 1200 ms hover-dwell preview; keep Public/Scientist as one dataset, two views.
- Run gates before declaring done: `pytest tests/backend/` and `npx playwright test --config tests/frontend/playwright.config.ts`.

---

## Phase 0 — Stabilize the refactor (do first, blocks the rest)

The two-pane workspace + anchored detail page is uncommitted and half-finished. Optimizing on an unstable surface wastes effort.

| Task | Detail | Acceptance |
|------|--------|-----------|
| P0.1 Finish anchored detail page | Verify `positionDrugDetailOverlay()` / `resolveDrugAnchorRect()` reposition correctly on scroll, resize, and back-nav; confirm `#drug/{id}` routing + back button restore filters | Open/close/deep-link a drug detail with no layout jump; Playwright p0-regression green |
| P0.2 Remove the dead modal | Delete `#modal-overlay` and any modal-only CSS/JS once the page covers all cases | Implemented: no `#modal-overlay` DOM; method names still carry legacy modal wording |
| P0.3 Wire scroll controls fully | Confirm `syncWorkspaceScrollControls()` fires on scroll/resize/filter; slider + ↑/↓ disabled when nothing to scroll | Controls track scroll position; disabled state correct on short lists |
| P0.4 Verify orphan-only path | `orphanDrugIds` populated at load; `applySpecialDrugFilters()` interacts correctly with disease + category filters | Orphan toggle yields correct counts in both views |
| P0.5 Commit the refactor | Branch, commit with a clear message, keep `Architecture.md`/`UI-Architecture.md` in sync | **Not done:** working tree remains uncommitted on `main`; docs have been updated |

---

## Phase 1 — High-leverage performance (UI + backend in parallel)

### Track A — Frontend rendering (U1, U2, U4, U5)

| Task | Detail | Acceptance |
|------|--------|-----------|
| A1 Decouple body map from `applyFilters()` (U1) | Only recompute region drug-counts when `activeCategory`/`activeBodyRegion` changes, not on search keystroke; cache counts, invalidate on data/index rebuild | **Done:** cached count helper + search `updateBodyMap: false`; Playwright regression green |
| A2 Debounce + incremental grid (U2) | Search input uses a short 40 ms debounce; mode switch preserves card DOM; result changes reconcile cards by `data-drug-id` | **Done:** `DrugGridRenderer` skips no-op signatures and moves/reuses cards |
| A3 De-duplicate cascades (U4) | Route clear-path updates through `handleSelectionCleared()` when `SelectionStore` has active selection; remove redundant region body-map update | **Done:** p0 regression asserts one region body-map update and clear-store path |
| A4 Diff disease D3 tree (U5) | Skip D3 update/rebuild when `currentRegionId`/`currentDiseaseId` signature is unchanged; update node highlight only | **Done:** p0 regression asserts root stability, zero `update()` calls, one highlight update |

### Track B — Backend correctness & latency (B1, B2, B3, B4, B5)

| Task | Detail | Acceptance |
|------|--------|-----------|
| B1 Fix graph-index staleness | Add mtime/source-hash check to `graph_index.py`; include graph source version in query-cache key; keep `/api/v1/admin/refresh`; warm the index at startup | **Done:** focused backend tests cover fallback/artifact source refresh and query cache versioning |
| B2 Async/threadpool targets DB | Move `routers/targets.py` off per-request sync `sqlite3` to the async pool in `db/connection.py` (or `run_in_threadpool`) | No sync DB calls on the event loop; targets endpoints unchanged externally |
| B3 Collapse target N+1 | Replace the 3 SELECTs in `GET /targets/{id}` with JOINs/batched query | Single round-trip; identical response shape |
| B4 Bound the open endpoints | Add `limit`/`offset` (+ caps) to `/drugs/search`, `/drugs/category/{c}`, `/diseases/search/{q}`, `/diseases/region/{r}`, `/diseases/{id}/drugs` | All list endpoints paginated; documented in README |
| B5 Replace `[:20]` slice | Give `/tree/disease/{id}` real pagination + a documented cap | No silent truncation |

---

## Phase 2 — Payload, polish, and accessibility

| Task | Detail | Acceptance |
|------|--------|-----------|
| C1 Shrink embed payload (U6) | Serve embeds gzip/Brotli on the static path; lazy-load graph bundles only when graph features are used | **Done:** generated sidecars, compression-aware server, Playwright compression assertion |
| C2 Detail-page a11y (U7) | Focus trap + focus restore on `#drug-detail-page`; `aria-modal`, labelled-by; `aria-live` on drug count; keyboard close/nav | **Partly done:** automated regressions cover detail semantics and mobile placement; axe scan not run |
| C3 Grid + D3 a11y semantics (U7) | `role`/`aria` on `#drug-grid`, cards, and D3 tree nodes; ensure keyboard activation | **Done for core paths:** cards and D3 nodes are keyboard-activatable; broader screen-reader QA still recommended |
| C4 Deepen Public/Scientist split (UI §8) | Hide SMILES/InChIKey/descriptors in Public; reveal available chemistry/lineage/provenance in Scientist | **Partly done:** raw SMILES hidden in Public; Scientist shows current canonical expert fields. cLogP/TPSA/HBA/HBD/provenance are not in canonical data yet |
| C5 ETL async migration (B6) | Migrate the 5 sync-`requests` ETL files to `httpx` with try/except + graceful degradation | **Done for imports/tests:** no sync `requests` in those files; full ETL run not checked |

---

## Phase 3 — Structural (optional / as capacity allows)

| Task | Detail | Acceptance |
|------|--------|-----------|
| D1 Extract from `app.js` (U9) | Follow `docs/ui/frontend-state-model.md` §8 order: DataLoader → DrugGridRenderer → PreviewController → FilterController → AtlasController → DetailController; keep each behind the same DOM contract | **Started:** DataLoader and DrugGridRenderer extracted; remaining controllers are future work |
| D2 Touch/mobile pass (U8) | Touch-equivalent for hover previews; responsive detail-page placement; verify atlas SVG interaction on touch | **Done for core flows:** touch dwell previews and mobile detail/topbar overflow verified by Playwright visual snapshot |
| D3 Split large backend modules (B7) | Break up `atc_orchestrator`, `drug_etl`, `disease_etl`, `validation_pipeline` by stage; add focused unit tests | No module >~600 lines in those areas; new tests cover the split |

---

## Sequencing & rationale

1. **Phase 0 is a hard prerequisite** — a half-migrated detail surface plus a vestigial modal is a correctness landmine. The detail surface and docs are now synchronized in the working tree; commit/push is still outside this plan update.
2. **Phase 1 runs two tracks in parallel.** Track A (U1 especially) is the cheapest, most visible UI win — kill the per-keystroke 14×O(n) body-map recompute first. Track B1 (graph staleness) is the most important *correctness* fix on the backend; B2/B3 are the latency fixes.
3. **Phase 2** is breadth: payload, accessibility, the Public/Scientist depth the product spec calls for, and ETL hygiene.
4. **Phase 3** is structural debt — valuable but lower urgency; do it when it unblocks the above rather than for its own sake.

## Definition of done (per task)
- Behavior verified in the running app (not just unit tests) for UI tasks; `pytest tests/backend/` for backend tasks.
- Playwright p0-regression green; visual snapshots captured under `.sisyphus/evidence/visual-snapshots/`; no new console errors in file-launch probe.
- Architecture docs updated if the change alters a documented contract or seam.
- For data-shape changes: embeds regenerated and the backend graph singleton refreshed/restarted.

## Open questions for the maintainer
1. **Hosting target for compression (C1):** local/test static hosting now serves sidecars. For GitHub Pages/CDN, confirm whether precompressed `.br`/`.gz` sidecars are honored or need deployment config.
2. **Backend in production:** is the FastAPI service actually deployed, or is the app effectively embed-only today? This re-ranks Track B vs. Track A.
3. **Detail-page vs modal:** answered for this implementation pass — the anchored in-panel page is treated as the current contract, and `#modal-overlay` was removed.
4. **Schema migration:** stay on the current flat record shape, or move toward the nested `docs/product/project-plan.md` Schema v1? This gates C4's depth.
