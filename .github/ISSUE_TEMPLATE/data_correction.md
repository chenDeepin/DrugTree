---
name: Data Correction
about: Correct errors in drug or disease information
title: '[Data Correction] <drug/disease name or ID>'
labels: 'data, correction'
assignees: ''
---

## Entity Type

- [ ] Drug
- [ ] Disease
- [ ] Disease-Drug Edge

## Entity Identifier

**Drug ID**: (e.g., `atorvastatin`, `simvastatin`)
**Disease ID**: (e.g., `hyperlipidemia`, `myocardial_infarction`)

## Field to Correct

Which field contains the error? (e.g., `atc_code`, `molecular_weight`, `body_region`, `name`)

## Current Value

```
Paste the current (incorrect) value here
```

## Proposed Value

```
Paste the corrected value here
```

## Source or Evidence

Provide supporting evidence for the correction:

- [ ] Official documentation (ChEMBL, DrugBank, PubChem, KEGG, FDA)
- [ ] Peer-reviewed publication
- [ ] Clinical trial data
- [ ] Other (please specify)

**Links or citations**:
- Link 1: ...
- Link 2: ...

## Additional Notes

Add any context about the correction (e.g., why current value is wrong, frequency of issue, etc.)

---

**IMPORTANT**: Remember that `src/frontend/data/*.json` files are generated from canonical sources. Please verify the correction applies to `data/drugs.json` or `data/diseases.json` at the repo root.
