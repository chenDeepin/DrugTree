# DrugTree Frontend - Application Guide

## Overview

Main frontend for DrugTree - visual drug exploration tool with ATC therapeutic classification.

**Stack**: Vanilla JS + RDKit.js | **Scale**: 1255 lines (`app.js`) + 61 drugs

---

## Quick Start

```bash
cd src/frontend && python3 -m http.server 8080
# Open http://localhost:8080
```

---

## File Structure

```
frontend/
├── index.html          # Entry (227 lines)
├── js/app.js           # DrugTreeApp class (1255 lines)
├── js/structure.js     # RDKit.js viewer
├── css/style.css       # Dark atlas theme (1158 lines)
└── data/drugs-full.json  # 61 drugs
```

---

## Key Methods

| Method | Purpose |
|--------|---------|
| `filterByCategory(cat)` | Filter by ATC category (14 categories) |
| `filterByBodyRegion(region)` | Filter by body region (14 regions) |
| `switchMode(mode)` | Switch Public/Scientist mode |
| `showDrugModal(drug)` | Display drug details + genealogy |
| `applyFilters()` | Combine category/body/search filters |

---

## Display Modes

- **Public Mode**: Simplified view, hides `.scientist-only` elements
- **Scientist Mode**: Full data, shows all drug properties

---

## Critical Anti-patterns

- **ALWAYS** use 1200ms hover delay (see `hoverDelay` property)
- **NEVER** skip mode check - test both modes
- **NEVER** hardcode ATC colors - use `ATC_CATEGORIES` object
- **NEVER** forget `initBodyMap()` call - body map won't render

---

## Common Tasks

**Add new drug**: Add to `drugs-full.json` with all required fields + valid SMILES

**Add ATC category**: Update `ATC_CATEGORIES` in `app.js` + CSS variable + filter button in HTML

**Modify body map**: Update `regions` array in `initBodyMap()` + SVG paths + ATC mapping

---

## Troubleshooting

**"Structure not loading"**: Check RDKit.js console errors + internet + SMILES validity

**"Body map not responding"**: Verify `initBodyMap()` called + `#body-map` element exists

**"Filters not working"**: Check `activeCategory` state + `applyFilters()` called + drug data structure

