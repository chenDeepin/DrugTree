# Contributing to DrugTree

Thank you for your interest in contributing! This guide will help you get started.

## Quick Start

```bash
# Clone the repository
git clone https://github.com/chenDeepin/DrugTree.git
cd DrugTree

# Install Python dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r src/backend/requirements.txt

# Start frontend (port 8080)
cd src/frontend && python3 -m http.server 8080

# Start backend (port 8000, optional)
uvicorn src.backend.main:app --reload --port 8000
```

## Contribution Types

We welcome contributions in these areas:

- **Code**: Bug fixes, new features, performance improvements
- **Data corrections**: Fixing errors in drug/disease information
- **Lineage corrections**: Adding or correcting drug genealogy relationships
- **New datasets**: Proposing additional data sources
- **Bug reports**: UI issues, crashes, unexpected behavior
- **Documentation**: Improving docs, adding examples, fixing typos

## Development Workflow

1. Fork the repository and create a feature branch
2. Make your changes following code style guidelines
3. Ensure tests pass: `pytest tests/backend/` and `npx playwright test`
4. Commit with clear, descriptive messages
5. Push to your fork and submit a pull request

## Code Style

- **JavaScript**: Vanilla JS, no build step, use existing patterns
- **Python**: Run `ruff format .` before committing, type hints preferred
- **Frontend**: Keep `src/frontend/data/*.json` files generated, never edit directly

## Testing Requirements

- All existing tests must pass before PR submission
- Add tests for new features and bug fixes
- Run Playwright e2e tests: `npx playwright test --config tests/frontend/playwright.config.ts`
- Run backend tests: `pytest tests/backend/`

## Data Contribution Rules

**IMPORTANT**: DrugTree uses canonical data sources in `data/` at the repo root.

- Edit canonical files: `data/drugs.json`, `data/diseases.json`, `data/disease_drug_edges.json`
- Regenerate frontend embeds after changes: `python3 scripts/build_frontend_embeds.py`
- Never edit `src/frontend/data/*.json` or `src/frontend/data/*.js` directly
- Disease filtering uses explicit edge-linked `drug_ids`, not body-region inference

## Critical Constraints

- Database files (`drugtree.db`, `*.sqlite`) are runtime artifacts, never commit
- ETL checkpoints and change logs in `data/changes/` are local state
- Keep valid ATC codes stable; placeholder codes need enrichment
- Wrap external data source calls in error handling with graceful degradation

## Review Process

- All PRs require at least one approval before merge
- Changes affecting canonical data require extra scrutiny
- Maintainers may request changes to tests, docs, or implementation
- CI runs automatically: linting, type checking, and full test suite

## Questions?

- Check existing docs: `README.md`, `docs/DATA_UPDATE_WORKFLOW.md`, architecture docs
- Open a discussion for questions or proposals
- Review open issues to avoid duplicates

Thanks for contributing! 🌳
