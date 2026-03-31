---
name: Dataset Proposal
about: Propose a new data source for DrugTree integration
title: '[Dataset] <dataset name or source>'
labels: 'enhancement, data, dataset'
assignees: ''
---

## Dataset Name

Name of the dataset or data source.

## Source URL

```
Primary URL where data can be accessed
```

## Data Format

- [ ] JSON
- [ ] XML
- [ ] REST API
- [ ] Database dump (SQL/CSV)
- [ ] Other: ...

## Key Fields

What fields does this dataset provide? (Select all that apply)

- [ ] Drug names and IDs
- [ ] Molecular structures (SMILES, InChI, InChIKey)
- [ ] ATC classification codes
- [ ] Therapeutic targets
- [ ] Mechanism of action
- [ ] Clinical trial data
- [ ] FDA approval status
- [ ] Side effects / adverse reactions
- [ ] Dosage information
- [ ] Drug-drug interactions
- [ ] Disease indications
- [ ] Pharmacokinetics
- [ ] Other: ...

## Estimated Records

Approximate number of records in the dataset.

## Update Frequency

How often is this dataset updated?

- [ ] Daily
- [ ] Weekly
- [ ] Monthly
- [ ] Quarterly
- [ ] Yearly
- [ ] Irregular
- [ ] Static (one-time)

## Therapeutic Relevance

Explain why this dataset would benefit DrugTree users:

- **Gap filled**: What missing information does this provide?
- **User value**: How would this improve exploration or research?
- **Use cases**: Specific examples of how users would benefit

## Integration Complexity

Rough estimate of integration effort:

- [ ] Simple (JSON/CSV with clear structure)
- [ ] Moderate (requires transformation or normalization)
- [ ] Complex (requires custom ETL, API integration, or significant parsing)

## Access Requirements

- [ ] Open access (no API key needed)
- [ ] Requires registration
- [ ] Requires API key or token
- [ ] Commercial / license required

If API key or registration required, provide details on the access process.

## Existing Overlap

Does this data overlap with existing sources (ChEMBL, DrugBank, PubChem, KEGG, FDA)?

- [ ] No overlap (new data)
- [ ] Partial overlap (enriches existing data)
- [ ] Full overlap (alternative source with better quality/coverage)

If overlap exists, explain why this source is preferred (e.g., more up-to-date, better quality, additional fields).

## Additional Notes

Any other relevant information about the dataset:

- Licensing or terms of use
- Data quality observations
- Known limitations or gaps
- Suggested integration approach
