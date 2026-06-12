# DrugTree Module Documentation

This folder contains focused module contracts. The root architecture maps stay in
`docs/Architecture.md` and `docs/UI-Architecture.md`; files here define the
individual backend/data/science modules those maps reference.

| Module | File | Purpose |
|---|---|---|
| Disease model | `disease-model.md` | Disease record shape, evidence levels, body-region placement, and API expectations. |
| Disease reasoning | `disease-reasoning.md` | Disease graph reasoning rules, pruning behavior, and no-go conditions for inferred links. |
| Graph data contract | `graph-data-contract.md` | Canonical graph artifact layout, node/edge envelopes, and export expectations. |
| Graph schema | `graph-schema.md` | Node and edge taxonomy for graph-native APIs and frontend consumers. |
| Graph transition plan | `graph-transition-plan.md` | Migration path from current JSON/SQLite surfaces to graph-aware artifacts. |
| Lineage model | `lineage-model.md` | Drug lineage edge semantics, generation rationale, and scoring model. |
| Lineage packs | `lineage-packs.md` | Curated flagship family plans and lineage evidence requirements. |
| Target layer readiness | `target-layer-readiness.md` | Target-node and drug-target edge prerequisites before target UX expansion. |
