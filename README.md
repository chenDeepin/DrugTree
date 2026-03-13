# 🌳 DrugTree

> A visual universe of drugs — explore structures, therapeutic areas, and drug generations at a glance.

## Vision

**Problem**: Drug databases are fragmented, require logins, and hide structures behind captchas. It's hard to see how drugs relate across generations or therapeutic areas.

**Solution**: An interactive human body map showing all drugs and clinical candidates, with one-click structure viewing and drug genealogy trees.

## Features

- 🗺️ **Human Body Map** - Click organs to explore drugs by therapeutic area
- 🧬 **Structure Viewer** - Instant 2D/3D molecular visualization
- 🌳 **Drug Genealogy** - See how drugs evolved across generations
- 🔍 **Developer-Friendly** - Open JSON/REST, no auth walls
- 📊 **Clinical Context** - Trial phases, targets, companies

## Quick Start

```bash
# Clone
git clone https://github.com/chenDeepin/DrugTree.git
cd DrugTree

# Open (Phase 1 MVP)
open src/frontend/index.html
```

## Documentation

- [Project Plan](docs/PROJECT_PLAN.md) - Full architecture and roadmap
- [Data Schema](docs/DATA_SCHEMA.md) - Drug data structure

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Vanilla JS + D3.js + 3Dmol.js |
| Backend | FastAPI (Python) |
| Data | ChEMBL + DrugBank + PubChem |
| Hosting | GitHub Pages (MVP) |

## Status

🚧 **Phase 1: MVP in development**

## License

MIT

## Author

Built by chenDeepin 🎯
