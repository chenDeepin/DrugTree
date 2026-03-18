#!/usr/bin/env python3
"""Analyze V-category drugs for potential reclassification."""

import json
import re
from collections import defaultdict

with open("data/drugs.json", "r") as f:
    drugs = json.load(f)["drugs"]

# Find valid V-category drugs
v_drugs = []
for d in drugs:
    code = d.get("atc_code", "")
    if code and code.startswith("V") and not code.startswith("V99"):
        v_drugs.append(d)

print(f"Total V-category drugs with valid ATC: {len(v_drugs)}")

# Analyze by V subcategory
by_sub = defaultdict(list)
for d in v_drugs:
    code = d.get("atc_code", "")
    subcat = code[1] if len(code) > 1 else ""
    by_sub[subcat].append(d)

for subcat in sorted(by_sub.keys()):
    count = len(by_sub[subcat])
    print(f"\nV{subcat} subcategory: {count} drugs")
    # Show examples
    for i in range(min(3, len(by_sub[subcat]))):
        d = by_sub[subcat][i]
        ind = (d.get("indication") or "No indication")[:50]
        print(f"  - {d.get('name')}: {ind}")
