import json

# Read the corrected drugs.json
with open('drugs.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"Total drugs to write: {len(data['drugs'])}")

# Write drugs using multi-line string
output = '''window.DRUGTREE_DRUGS_DATA = {
  "drugs": [
'''

for i in range(len(data['drugs'])):
    output += '''  {{
      "id": "%s",
      "name": "%s",
      "smiles": "%s",
      "inchikey": "%s",
      "atc_code": "%s",
      "atc_category": "%s",
      "molecular_weight": %s,
      "phase": "%s",
      "year_approved": "%s",
      "generation": "%s",
      "indication": "%s",
        "targets": json.dumps(drug.get("targets", [])).replace('None', 'null').replace('[]', '[]'),
      "company": "%s",
      "synonyms": %s,
      "class": "%s",
      "clinical_trials": %s,
      "kegg_id": "%s",
      "herin_region": "%s",
      "secondary_body_regions": %s
    }}''' % (
        drug["id"],
        drug["name"].replace('\\', r'\\\\').replace('"', r'\"'),
        drug.get("smiles", "").replace('\\', r'\\\\'),
        drug.get("inchikey", ""),
        drug.get("atc_code", "Unknown"),
        drug.get("atc_category", "Unknown"),
        str(drug.get("molecular_weight", 0)),
        drug.get("phase", "Unknown"),
        "None" if drug.get("year_approved") is None else "null",
        "None" if drug.get("generation") is None else "null",
        "None" if drug.get("indication") is None else "null",
        json.dumps(drug.get("targets", [])).replace('None', 'null').replace('None', 'null').replace('[]', '[]').replace('[]', '[]'),
        "None" if drug.get("class") is None else "null",
        json.dumps(drug.get("clinical_trials", [])).replace('None', '[]').replace('[]', '[]'),
        drug.get("kegg_id", ""),
        drug.get("herin_region", ""),
        json.dumps(drug.get("secondary_body_regions", [])).replace('None', '[]').replace('[]', '[]')
    )
    
    if i < len(data['drugs']):
        output += ',\\n    \n'
    else:
        output += '\n'

output += '  ]\n};\n'

# Write to file
with open('drugs.js', 'w', encoding='utf-8') as f:
    f.write(output)

print("Successfully wrote drugs.js")
PYEOF
