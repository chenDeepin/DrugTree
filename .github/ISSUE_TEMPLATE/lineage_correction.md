---
name: Lineage Correction
about: Add or correct drug genealogy relationships
title: '[Lineage] <drug A> → <drug B> relationship'
labels: 'data, lineage, genealogy'
assignees: ''
---

## Current Relationship

**From Drug**: (drug ID or name, e.g., `omeprazole`)
**To Drug**: (drug ID or name, e.g., `lansoprazole`)

**Edge Type**: (if known)
- [ ] follow_on
- [ ] derivative
- [ ] mechanism_evolution
- [ ] scaffold_variant
- [ ] unknown

**Current Edge ID**: (if existing edge exists, e.g., `omeprazole_to_lansoprazole`)

## Proposed Change

What should the relationship be?

- [ ] Add new edge
- [ ] Modify existing edge
- [ ] Remove edge
- [ ] Change edge type

**New/Corrected Edge Type**:
```
(e.g., follow_on, derivative, mechanism_evolution, scaffold_variant)
```

## Rationale

Explain why this relationship exists or should be corrected:

- **Timeline**: Drug A approved in [year], Drug B approved in [year]
- **Mechanism**: Both target [mechanism/protein], Drug B improved [specific aspect]
- **Scaffold**: Drug B modified the core structure by [description]
- **Literature**: See [link to paper or documentation]

## Confidence Level

How confident are you in this relationship?

- [ ] High (strong evidence: patents, publications, official documentation)
- [ ] Medium (reasonable inference: mechanistic similarity, structural clues)
- [ ] Low (speculative: structural similarity only, indirect evidence)

## Supporting Evidence

Provide sources supporting this relationship:

1. **Source**: (e.g., patent, paper, FDA approval letter)
   **Link**: ...
   **Relevant excerpt**: ...

2. **Source**:
   **Link**: ...
   **Relevant excerpt**: ...

## Additional Context

Any other relevant information:
- Other related drugs in this lineage
- Why this relationship matters for the genealogy
- Notes on confidence level
