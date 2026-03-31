# DrugTree Frontend JS Architecture

## OVERVIEW
Frontend JS layer for DrugTree, centered on app.js plus shared state, stores, views, and components.

## KEY FILES
app.js, main app runtime, boot flow, routing, filters, listeners, card rendering.
app-state.js, state helpers, body region labels, summaries, category toggles.
structure.js, RDKit.js SMILES to 2D SVG rendering.
stores/graphStore.js, graph load and pub/sub state updates.
stores/selectionStore.js, current selection events and view changes.
components/, approval chips, disease panel, mechanism card, orphan badge.
views/, disease tree and genealogy tree rendering.

## ARCHITECTURE PATTERNS
API first, local embeds as fallback.
Hash routing drives detail navigation.
Single shared state, then derived views and cards.
Event driven stores, emit on change, subscribe in UI.
Filter composition, category, search, body region, disease edges.
RDKit preview only when structure data exists.

## CONVENTIONS
Keep DOM logic near the feature file.
Prefer small helpers over deep inline branches.
Use existing label and summary utilities.
Preserve 1200ms hover delay for region and ATC previews.
Respect ATC palette and badge metadata.

## ANTI-PATTERNS
Do not edit generated data mirrors here.
Do not bypass API fetch fallbacks.
Do not break #drug/{id} routing.
Do not clear unrelated selection state.
Do not hardcode new ATC colors or labels.
