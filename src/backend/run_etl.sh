#!/bin/bash
# Run DrugTree ETL Pipeline

set -e  # Exit on error

# Configuration
COMPOUND_MASTER_TABLE="/media/chen/Machine_Disk/Python script/ClinicalMol_hier/data/processed/compound_master_table.tsv"
OUTPUT_JSON="../frontend/data/drugs.json"
OUTPUT_ALIAS="../frontend/data/drugs-expanded.json"
CACHE_FILE="kegg_cache.json"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== DrugTree ETL Pipeline ===${NC}"
echo ""

# Check if input file exists
if [ ! -f "$COMPOUND_MASTER_TABLE" ]; then
    echo -e "${RED}ERROR: Input file not found: $COMPOUND_MASTER_TABLE${NC}"
    exit 1
fi

echo -e "${YELLOW}Input: $COMPOUND_MASTER_TABLE${NC}"
echo -e "${YELLOW}Output: $OUTPUT_JSON${NC}"
echo -e "${YELLOW}Alias:  $OUTPUT_ALIAS${NC}"
echo ""

# Run ETL
echo -e "${GREEN}Running ETL pipeline...${NC}"
python3 -m etl.drug_etl \
    --input "$COMPOUND_MASTER_TABLE" \
    --output "$OUTPUT_JSON" \
    --cache "$CACHE_FILE" \
    "$@"  # Pass any additional arguments

cp "$OUTPUT_JSON" "$OUTPUT_ALIAS"
python3 ../../scripts/build_frontend_embeds.py

echo ""
echo -e "${GREEN}ETL pipeline complete!${NC}"
echo -e "Output saved to: ${YELLOW}$OUTPUT_JSON${NC}"
echo -e "Alias updated:   ${YELLOW}$OUTPUT_ALIAS${NC}"
