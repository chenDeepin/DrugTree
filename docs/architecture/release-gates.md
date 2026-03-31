# DrugTree Release Gates: Waves 1-4 Consolidation

## Scope and authority

This document is the release-gated roadmap for the frontend stabilization program and subsequent expansion readiness.

- Master sequencing authority: `.sisyphus/plans/current-stage-next-stage-plan.md`
- Consolidated architecture sources:
  - `docs/frontend-state-model.md`
  - `docs/architecture/graph-schema.md`
  - `docs/architecture/lineage-model.md`
  - `docs/architecture/disease-model.md`
  - `docs/architecture/graph-data-contract.md`
  - `docs/architecture/graph-transition-plan.md`
  - `docs/architecture/lineage-packs.md`
  - `docs/architecture/disease-reasoning.md`
  - `docs/architecture/target-layer-readiness.md`

---

## Release Principle RP-1: Stability Before Expansion

**Definition**: No work in scientific expansion scope may start until stabilization and architecture cleanup evidence is complete and verifiable.

### RP-1 concrete checks

| Check ID | Requirement | Pass condition |
|---|---|---|
| RP1-A | P0 interaction defects closed | Wave 1 exit gate signed with evidence from T1-T6 code paths |
| RP1-B | State/render boundaries documented and tested | Wave 2 exit gate signed with `docs/frontend-state-model.md` + `tests/frontend/e2e/p0-regression.spec.ts` |
| RP1-C | Graph contracts defined before graph-native changes | Wave 3 exit gate signed with T12-T14 docs |
| RP1-D | Expansion plans reference stable contracts only | Wave 4 docs explicitly anchor to T12-T14 contracts and do not bypass prior gates |

**Enforcement rule**: If any RP1 check fails, progression to the next release stage is blocked.

---

## Wave-by-wave summary with exit gates and evidence

## Wave 1 — P0 Stabilization (T1-T6)

**Purpose**: Eliminate critical frontend interaction regressions so the UI is behaviorally predictable before architectural work.

| Element | Details |
|---|---|
| Tasks completed | T1 Dropdown hardening; T2 Selection source-of-truth consolidation; T3 View-mode event loop fix; T4 Body-region highlight layer separation; T5 Genealogy interaction cleanup; T6 Tooltip clamping and responsive fixes |
| Exit gate | All P0 interaction paths behave deterministically (dropdown close/open, selection persistence, view switching, highlight isolation, genealogy interaction, tooltip clamping) and are no longer dependent on fragile parallel state |
| Evidence artifacts created | Code-path evidence in `src/frontend/js/app.js`, `src/frontend/css/style.css`, `src/frontend/js/components/disease-panel.js`, `src/frontend/js/views/genealogyView.js`; plan acceptance/QA scenarios in `.sisyphus/plans/current-stage-next-stage-plan.md` |

## Wave 2 — P1 Architecture Cleanup (T7-T11)

**Purpose**: Freeze and document frontend state ownership and rendering boundaries so future changes are constrained by explicit contracts.

| Element | Details |
|---|---|
| Tasks completed | T7 Frontend state model doc; T8 Module extraction seams; T9 Render boundary map; T10 Event-driven rendering alignment; T11 P0 regression suite expansion |
| Exit gate | State ownership, event flow, and render boundaries are documented, and P0 regressions are encoded as executable tests |
| Evidence artifacts created | `docs/frontend-state-model.md` (state inventory, ownership, event flows, boundary rules); `tests/frontend/e2e/p0-regression.spec.ts` (regression gate suite) |

## Wave 3 — P2/P4 Foundation (T12-T16)

**Purpose**: Publish architecture contracts and transition plans so graph evolution can proceed without API/UI destabilization.

| Element | Details |
|---|---|
| Tasks completed | T12 public model docs (`graph-schema.md`, `lineage-model.md`, `disease-model.md`); T13 graph data contract; T14 phased graph transition plan; T15 contributor/docs templates; T16 README/public polish |
| Exit gate | Graph node/edge semantics, data layout contract, and migration phases are explicit, versioned, and rollback-aware |
| Evidence artifacts created | `docs/architecture/graph-schema.md`; `docs/architecture/lineage-model.md`; `docs/architecture/disease-model.md`; `docs/architecture/graph-data-contract.md`; `docs/architecture/graph-transition-plan.md`; contributor/public docs from T15-T16 |

## Wave 4 — P3 Scientific Expansion (T17-T20)

**Purpose**: Define scientific expansion tracks (lineage, disease reasoning, target layer) that are gated by prior stabilization and contract evidence.

| Element | Details |
|---|---|
| Tasks completed | T17 flagship lineage pack plan; T18 disease reasoning cleanup plan; T19 target-layer readiness plan; T20 release-gate consolidation |
| Exit gate | Expansion plans remain design-stage only, reference Wave 3 contracts, and include explicit no-go conditions to prevent unsafe activation |
| Evidence artifacts created | `docs/architecture/lineage-packs.md`; `docs/architecture/disease-reasoning.md`; `docs/architecture/target-layer-readiness.md`; `docs/architecture/release-gates.md` |

---

## Cross-wave dependency graph (blocking relationships)

```text
Wave 1 (T1-T6) ──blocks──> Wave 2 (T7-T11)
Wave 2 (T7-T11) ──blocks──> Wave 3 (T12-T16)
Wave 3 (T12-T16) ──blocks──> Wave 4 (T17-T20)

T20 (release gates) requires: T8, T9, T10, T11, T12, T13, T14, T15, T16, T17, T18, T19
Final Verification requires: T20 complete

No backward bypass allowed:
- Wave 4 cannot start if Wave 1 or Wave 2 exit evidence is missing
- Graph rollout phases cannot start if Wave 3 contracts are incomplete
```

---

## Release stages and explicit gating criteria

## Stage 1 — Stabilization

| Gate | Required evidence | Blockers if unmet |
|---|---|---|
| S1-G1 | Wave 1 completion evidence (T1-T6 code-path fixes) | Any unresolved P0 interaction inconsistency |
| S1-G2 | Deterministic selection/view behavior proven in app flows | Parallel state truth still present in critical paths |
| S1-G3 | Baseline smoke verification of affected interactions | Inability to reproduce stable dropdown/highlight/genealogy behavior |

## Stage 2 — Architecture Cleanup

| Gate | Required evidence | Blockers if unmet |
|---|---|---|
| S2-G1 | `docs/frontend-state-model.md` published and aligned to current behavior | State ownership ambiguity across app/store/components |
| S2-G2 | Render/event boundary definitions (T8-T10 outputs) complete | Rendering side effects crossing undocumented boundaries |
| S2-G3 | `tests/frontend/e2e/p0-regression.spec.ts` active as regression gate | P0 regressions not encoded as executable guardrails |

## Stage 3 — Graph Contracts

| Gate | Required evidence | Blockers if unmet |
|---|---|---|
| S3-G1 | T12 core model docs published (`graph-schema`, `lineage-model`, `disease-model`) | Undefined node/edge semantics |
| S3-G2 | `graph-data-contract.md` defines canonical v2 layout + metadata contract | No uniform edge metadata/curation status contract |
| S3-G3 | `graph-transition-plan.md` defines phased rollout with rollback points | Big-bang migration risk; no fallback-first path |

## Stage 4 — Scientific Expansion

| Gate | Required evidence | Blockers if unmet |
|---|---|---|
| S4-G1 | `lineage-packs.md` quality gates and merge checklist defined | Lineage curation proceeds without minimum quality/provenance thresholds |
| S4-G2 | `disease-reasoning.md` enforces explicit edge-backed disease-drug logic | Any inference-by-region replacing explicit disease-drug edges |
| S4-G3 | `target-layer-readiness.md` scientist-only phased rollout and rollback defined | Target UX leaks into public mode or lacks rollback-safe phases |
| S4-G4 | This release-gate document (T20) confirms RP-1 compliance across Waves 1-4 | Premature expansion without stabilization evidence |

---

## Gating conditions preventing premature expansion

The following are hard stop conditions for any implementation-phase expansion work:

1. **Missing prior-wave exit evidence**: No stage may begin if the previous stage has unclosed gate items.
2. **Contract-first violation**: No graph-native implementation without Stage 3 contract artifacts (`graph-data-contract.md`, `graph-transition-plan.md`).
3. **Public-mode safety violation**: No target-layer activation unless scientist-only gating and rollback criteria are defined and testable.
4. **Inference-over-evidence violation**: No disease feature may replace explicit disease-drug edges with region/category inference.
5. **Regression blind spot**: No expansion work if P0 regression suite is absent, stale, or not part of release verification.
6. **Unphased migration**: Any proposal that skips dual-source/adapter/fallback phases is blocked.

---

## Implementation-phase entry criteria (go/no-go)

Implementation beyond planning is allowed only when all conditions are true:

| Criteria ID | Go condition |
|---|---|
| GO-1 | Stage 1 and Stage 2 gates are fully passed with evidence |
| GO-2 | Stage 3 contracts are published and internally consistent |
| GO-3 | Stage 4 plans explicitly reference Stage 3 contracts and keep planning-only boundaries where required |
| GO-4 | Cross-wave dependency graph has no unmet upstream blockers |
| GO-5 | Final verification is scheduled after T20 and before any new expansion sprint |

If any GO condition fails, status is **NO-GO** and scope is limited to closing unmet gates.
