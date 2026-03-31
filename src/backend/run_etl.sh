#!/bin/bash
# Run the canonical DrugTree ETL pipeline.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Configuration
COMPOUND_MASTER_TABLE="/media/chen/Machine_Disk/Python script/ClinicalMol_hier/data/processed/compound_master_table.tsv"
OUTPUT_JSON="${PROJECT_ROOT}/data/drugs.json"
CACHE_FILE="${SCRIPT_DIR}/kegg_cache.json"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== DrugTree ETL Pipeline ===${NC}"
echo ""

if [ ! -f "$COMPOUND_MASTER_TABLE" ]; then
    echo -e "${RED}ERROR: Input file not found: $COMPOUND_MASTER_TABLE${NC}"
    exit 1
fi

echo -e "${YELLOW}Input:  $COMPOUND_MASTER_TABLE${NC}"
echo -e "${YELLOW}Output: $OUTPUT_JSON${NC}"
echo ""

echo -e "${GREEN}Running drug ETL...${NC}"
python3 "${SCRIPT_DIR}/etl/drug_etl.py" \
    --input "$COMPOUND_MASTER_TABLE" \
    --output "$OUTPUT_JSON" \
    --cache "$CACHE_FILE" \
    "$@"

echo -e "${GREEN}Rebuilding disease graph artifacts...${NC}"
python3 "${SCRIPT_DIR}/etl/disease_etl.py"

echo -e "${GREEN}Building graph-native artifacts...${NC}"
python3 "${PROJECT_ROOT}/scripts/build_graph_artifacts.py"

echo -e "${GREEN}Refreshing frontend embeds...${NC}"
python3 "${PROJECT_ROOT}/scripts/build_frontend_embeds.py"

echo ""
echo -e "${GREEN}ETL pipeline complete!${NC}"
echo -e "Canonical drug data: ${YELLOW}$OUTPUT_JSON${NC}"
