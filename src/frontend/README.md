# DrugTree - Visual Drug Universe with ATC Classification

## Overview

DrugTree is an interactive visualization tool for exploring approved small molecule drugs organized by WHO ATC (Anatomical Therapeutic Chemical) classification system.

## Features

- **61 Real Small Molecule Drugs** with verified SMILES structures
- **14 ATC Level 1 Categories** with color-coded navigation
- **Interactive Structure Rendering** using RDKit.js
- **Enhanced Drug Cards** with comprehensive information
- **Search and Filter** by name, target, class, or ATC code

## ATC Categories

| Code | Category | Drugs | Color |
|------|----------|-------|-------|
| A | Alimentary Tract & Metabolism | 6 | Green |
| B | Blood & Blood-forming Organs | 5 | Red |
| C | Cardiovascular System | 6 | Pink |
| D | Dermatologicals | 3 | Orange |
| G | Genito-urinary System & Sex Hormones | 4 | Purple |
| H | Systemic Hormonal Preparations | 4 | Brown |
| J | Anti-infectives for Systemic Use | 6 | Blue |
| L | Antineoplastic & Immunomodulating Agents | 6 | Dark Red |
| M | Musculo-skeletal System | 4 | Grey |
| N | Nervous System | 6 | Deep Purple |
| P | Antiparasitic Products | 3 | Teal |
| R | Respiratory System | 4 | Cyan |
| S | Sensory Organs | 2 | Indigo |
| V | Various | 2 | Grey |

## File Structure

```
frontend/
├── index.html          # Main HTML with ATC category sidebar
├── css/
│   └── style.css       # Styling with 14 ATC category colors
├── js/
│   ├── app.js          # Main application with ATC support
│   ├── structure.js    # RDKit.js structure rendering
│   └── body-map.js     # (Legacy) body map handler
├── data/
│   ├── drugs-full.json # 61 drugs with complete ATC data
│   └── sample-drugs.json # (Legacy) original 22 drugs
└── assets/
    └── human-body.svg  # (Optional) body map SVG
```

## Data Format

Each drug in `drugs-full.json` contains:

```json
{
  "id": "atorvastatin",
  "name": "Atorvastatin",
  "smiles": "CC(C)C1=C(C(=C(N1CCC(CC(CC(=O)O)O)O)C2=CC=C(C=C2)F)C3=CC=CC=C3)C(=O)NC4=CC=CC=C4",
  "inchikey": "XUKUURHRXDUEBC-UHFFFAOYSA-N",
  "atc_code": "C10AA05",
  "atc_category": "C",
  "molecular_weight": 558.64,
  "phase": "IV",
  "year_approved": 1996,
  "generation": 2,
  "indication": "Hypercholesterolemia, cardiovascular disease",
  "targets": ["HMG-CoA reductase"],
  "company": "Pfizer",
  "synonyms": ["Lipitor", "Sortis"],
  "class": "Statin"
}
```

## How to Test

1. Serve the frontend directory with any HTTP server:
   ```bash
   cd /media/chen/Machine_Disk/AgentDrugDiscov/Telegram_sessions/DrugTree/src/frontend
   python3 -m http.server 8080
   ```

2. Open `http://localhost:8080` in your browser

3. Test features:
   - Click ATC category buttons to filter drugs
   - Search for drugs by name, target, or class
   - Click a drug card to see detailed information
   - Click ATC code in modal to filter by that category
   - Copy SMILES with the copy button
   - Verify structure rendering (requires internet for RDKit.js CDN)

## Dependencies

- RDKit.js (loaded from CDN: unpkg.com/@rdkit/rdkit)
- No other external dependencies required

## Browser Compatibility

- Modern browsers with ES6+ support
- Chrome, Firefox, Safari, Edge (latest versions)

---

*Generated: 2026-03-13*
*Version: 2.0 - ATC Classification*
