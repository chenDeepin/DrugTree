# DrugTree — Next Round Plan (UI + Backend Optimization)

**Date:** 2026-06-12 · **Branch:** `main` · **Base commit:** `34933f0`
**Goal of this round:** Land the in-progress two-pane refactor cleanly, then take the highest-leverage UI and backend optimizations in parallel without breaking the JSON-first / embed-fallback / no-build-step invariants.
**Inputs:** [2026-06-12-review-qa.md](./2026-06-12-review-qa.md) (findings), [../Architecture.md](../Architecture.md), [../UI-Architecture.md](../UI-Architecture.md).

Issue IDs below reference the optimization tables in the architecture docs (`U#` = UI-Architecture §9, `B#` = Architecture §6).

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
| P0.2 Remove the dead modal | Delete `#modal-overlay` (index.html:347) and any modal-only CSS/JS once the page covers all cases | No references to `#modal-overlay`; no console errors |
| P0.3 Wire scroll controls fully | Confirm `syncWorkspaceScrollControls()` fires on scroll/resize/filter; slider + ↑/↓ disabled when nothing to scroll | Controls track scroll position; disabled state correct on short lists |
| P0.4 Verify orphan-only path | `orphanDrugIds` populated at load; `applySpecialDrugFilters()` interacts correctly with disease + category filters | Orphan toggle yields correct counts in both views |
| P0.5 Commit the refactor | Branch, commit with a clear message, keep `Architecture.md`/`UI-Architecture.md` in sync | Clean working tree; docs reflect shipped state |

---

## Phase 1 — High-leverage performance (UI + backend in parallel)

### Track A — Frontend rendering (U1, U2, U4, U5)

| Task | Detail | Acceptance |
|------|--------|-----------|
| A1 Decouple body map from `applyFilters()` (U1) | Only recompute region drug-counts when `activeCategory`/`activeBodyRegion` changes, not on search keystroke; cache counts, invalidate on category/region change | No body-map recompute on text search (verify via profiling/log); counts still correct |
| A2 Debounce + incremental grid (U2) | Debounce search input (~150–250 ms); make mode switch a CSS class toggle, not a grid rebuild; move toward append/remove card diffing instead of full `innerHTML` | Typing doesn't rebuild 120 cards/keystroke; mode toggle does zero card recreation |
| A3 De-duplicate cascades (U4) | Route all clear-path updates through `handleSelectionCleared()` only; remove the redundant `updateBodyMapState()` double-call in `handleRegionSelected()` | Each boundary renders once per user action (instrument to confirm) |
| A4 Diff disease D3 tree (U5) | Skip `diseaseView.render()` rebuild when `currentRegionId`/`currentDiseaseId` unchanged; update node highlight only | Re-selecting same region does not rebuild SVG |

### Track B — Backend correctness & latency (B1, B2, B3, B4, B5)

| Task | Detail | Acceptance |
|------|--------|-----------|
| B1 Fix graph-index staleness | Add mtime/source-hash check to `graph_index.py` (mirror `DataSnapshotService`) or an `/api/v1/admin` refresh hook that calls `refresh()`; warm the index at startup | After ETL + refresh, graph endpoints serve new data without full restart |
| B2 Async/threadpool targets DB | Move `routers/targets.py` off per-request sync `sqlite3` to the async pool in `db/connection.py` (or `run_in_threadpool`) | No sync DB calls on the event loop; targets endpoints unchanged externally |
| B3 Collapse target N+1 | Replace the 3 SELECTs in `GET /targets/{id}` with JOINs/batched query | Single round-trip; identical response shape |
| B4 Bound the open endpoints | Add `limit`/`offset` (+ caps) to `/drugs/search`, `/drugs/category/{c}`, `/diseases/search/{q}`, `/diseases/region/{r}`, `/diseases/{id}/drugs` | All list endpoints paginated; documented in README |
| B5 Replace `[:20]` slice | Give `/tree/disease/{id}` real pagination + a documented cap | No silent truncation |

---

## Phase 2 — Payload, polish, and accessibility

| Task | Detail | Acceptance |
|------|--------|-----------|
| C1 Shrink embed payload (U6) | Serve embeds gzip/Brotli on the static path; trim unused shell fields; consider splitting `graph-nodes.js` further or loading it only when graph features are used | Measurable drop in transferred bytes for first paint |
| C2 Detail-page a11y (U7) | Focus trap + focus restore on `#drug-detail-page`; `aria-modal`, labelled-by; `aria-live` on drug count; keyboard close already exists — extend to nav | Keyboard-only open/close/navigate works; axe scan clean on detail surface |
| C3 Grid a11y + semantics (U7) | `role`/`aria` on `#drug-grid` and cards; ensure scroll controls are keyboard-operable | Screen-reader can enumerate results; controls reachable by Tab |
| C4 Deepen Public/Scientist split (UI §8) | Hide SMILES/InChIKey/descriptors in Public; reveal full chemistry/lineage/provenance in Scientist | Public card has no raw SMILES; Scientist shows expert fields |
| C5 ETL async migration (B6) | Migrate the 5 sync-`requests` ETL files to `httpx` with try/except + graceful degradation | No `import requests` in those files; ETL run still succeeds |

---

## Phase 3 — Structural (optional / as capacity allows)

| Task | Detail | Acceptance |
|------|--------|-----------|
| D1 Extract from `app.js` (U9) | Follow `docs/ui/frontend-state-model.md` §8 order: DataLoader → DrugGridRenderer → PreviewController → FilterController → AtlasController → DetailController; keep each behind the same DOM contract | `app.js` shrinks; behavior unchanged; tests green |
| D2 Touch/mobile pass (U8) | Touch-equivalent for hover previews; responsive detail-page placement; verify atlas SVG interaction on touch | Core flows usable on a phone viewport |
| D3 Split large backend modules (B7) | Break up `atc_orchestrator`, `drug_etl`, `disease_etl`, `validation_pipeline` by stage; add focused unit tests | No module >~600 lines in those areas; new tests cover the split |

---

## Sequencing & rationale

1. **Phase 0 is a hard prerequisite** — a half-migrated detail surface plus a vestigial modal is a correctness landmine. Land it, commit it, sync the docs.
2. **Phase 1 runs two tracks in parallel.** Track A (U1 especially) is the cheapest, most visible UI win — kill the per-keystroke 14×O(n) body-map recompute first. Track B1 (graph staleness) is the most important *correctness* fix on the backend; B2/B3 are the latency fixes.
3. **Phase 2** is breadth: payload, accessibility, the Public/Scientist depth the product spec calls for, and ETL hygiene.
4. **Phase 3** is structural debt — valuable but lower urgency; do it when it unblocks the above rather than for its own sake.

## Definition of done (per task)
- Behavior verified in the running app (not just unit tests) for UI tasks; `pytest tests/backend/` for backend tasks.
- Playwright p0-regression green; no new console errors.
- Architecture docs updated if the change alters a documented contract or seam.
- For data-shape changes: embeds regenerated and the backend graph singleton refreshed/restarted.

## Open questions for the maintainer
1. **Hosting target for compression (C1):** is the static host GitHub Pages only, or is there a CDN/server that can do Brotli? This decides whether C1 is build-time pre-compression or server config.
2. **Backend in production:** is the FastAPI service actually deployed, or is the app effectively embed-only today? This re-ranks Track B vs. Track A.
3. **Detail-page vs modal:** confirm the anchored in-panel page is the intended final design (not a reversible experiment) before P0.2 deletes the modal.
4. **Schema migration:** stay on the current flat record shape, or move toward the nested `docs/product/project-plan.md` Schema v1? This gates C4's depth.
