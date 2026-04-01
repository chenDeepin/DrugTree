# DrugTree Backend Migrations

## OVERVIEW
Local rules for `src/backend/migrations/` only. Inherit `src/backend/AGENTS.md`; this file adds migration-specific constraints for SQL files and the migration runner.

## WHERE TO LOOK
- `run_migration.py` - discovers `*.sql` files and records applied state by filename.
- `001_add_disease_tables.sql` - example of additive SQLite-safe tables, indexes, FTS, and triggers.
- `003_graph_schema.sql` - example of additive schema expansion with inline preservation notes.
- `../validation/migration_validator.py` - report-only validation; current pass bar is coverage >= 95% and zero critical discrepancies.

## CONVENTIONS
- Prefer additive, idempotent SQL (`IF NOT EXISTS`, guarded indexes/triggers) so migrations stay safe against partially initialized databases.
- Preserve existing rows in place; when schema shape changes, stage it as add/backfill/switch/cleanup instead of a one-step destructive rewrite.
- Keep SQLite compatibility first unless the file clearly documents a justified engine-specific branch.
- Add a short header comment stating intent, affected tables, and any data-preservation assumptions.

## REVERSIBILITY
- Any destructive or non-obvious data transform must include an inline rollback note, or explicitly state that it is not safely reversible.
- If rollback would be lossy, prefer a follow-up corrective migration over silent table rewrites or in-place drops.
- Do not rename reviewed migration files; applied state is tracked by filename.

## REVIEW GATE
- A migration is not review-ready unless the diff makes data-loss risk, rollback plan, and affected tables or columns obvious to a reviewer.
- Changes that can affect frontend-required drug fields or overall row coverage should point reviewers to `../validation/migration_validator.py`; that validator reports discrepancies only and must not become an auto-fix path.
- Keep workflow instructions out of individual SQL files; document intent and safety notes, not mandatory execution commands.

## ANTI-PATTERNS
- Destructive `DROP` or rewrite-first migrations without a staged preservation plan.
- Unannotated engine-specific SQL that breaks SQLite compatibility by surprise.
- Editing old reviewed migration files to change applied behavior instead of adding a new migration.
