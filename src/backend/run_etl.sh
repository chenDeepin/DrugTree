#!/bin/bash
# Run the canonical DrugTree ETL pipeline.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Configuration
DEFAULT_COMPOUND_MASTER_TABLE="${PROJECT_ROOT}/data/processed/compound_master_table.tsv"
COMPOUND_MASTER_TABLE="${COMPOUND_MASTER_TABLE:-$DEFAULT_COMPOUND_MASTER_TABLE}"
OUTPUT_JSON="${PROJECT_ROOT}/data/drugs.json"
CACHE_FILE="${SCRIPT_DIR}/kegg_cache.json"
ETL_CORE_TIMEOUT_SECONDS="${ETL_CORE_TIMEOUT_SECONDS:-1800}"
ETL_STEP_TIMEOUT_SECONDS="${ETL_STEP_TIMEOUT_SECONDS:-300}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== DrugTree ETL Pipeline ===${NC}"
echo ""

if [ ! -f "$COMPOUND_MASTER_TABLE" ]; then
    echo -e "${RED}ERROR: Input file not found: $COMPOUND_MASTER_TABLE${NC}"
    echo -e "${YELLOW}Expected default: ${DEFAULT_COMPOUND_MASTER_TABLE}${NC}"
    echo -e "${YELLOW}Set COMPOUND_MASTER_TABLE before running, or place the file at the default path.${NC}"
    exit 1
fi

echo -e "${YELLOW}Input:  $COMPOUND_MASTER_TABLE${NC}"
echo -e "${YELLOW}Output: $OUTPUT_JSON${NC}"
echo -e "${YELLOW}Core step timeout: ${ETL_CORE_TIMEOUT_SECONDS}s${NC}"
echo -e "${YELLOW}Optional step timeout: ${ETL_STEP_TIMEOUT_SECONDS}s${NC}"
echo ""

run_required_step() {
    local label="$1"
    shift

    if ! timeout "${ETL_CORE_TIMEOUT_SECONDS}s" "$@"; then
        echo -e "${RED}ERROR: ${label} failed or timed out after ${ETL_CORE_TIMEOUT_SECONDS}s${NC}"
        exit 1
    fi
}

run_optional_step() {
    local label="$1"
    shift

    if ! timeout "${ETL_STEP_TIMEOUT_SECONDS}s" "$@"; then
        echo -e "${RED}WARNING: ${label} failed or timed out after ${ETL_STEP_TIMEOUT_SECONDS}s${NC}"
    fi
}

echo -e "${GREEN}Running drug ETL...${NC}"
run_required_step "drug ETL" python3 "${SCRIPT_DIR}/etl/drug_etl.py" \
    --input "$COMPOUND_MASTER_TABLE" \
    --output "$OUTPUT_JSON" \
    --cache "$CACHE_FILE" \
    "$@"

echo -e "${GREEN}Rebuilding disease graph artifacts...${NC}"
run_required_step "disease graph artifacts" python3 "${SCRIPT_DIR}/etl/disease_etl.py"

echo ""

echo -e "${GREEN}=== Phase 2: External Source Extraction ===${NC}"
echo ""

EXTRACT_SCRIPTS=(
    "fetch_drugcentral.py"
    "fetch_opentargets.py"
    "fetch_dgidb.py"
    "fetch_rxnorm.py"
    "fetch_ttd.py"
    "fetch_ctd.py"
    "fetch_clinicaltrials.py"
    "fetch_drugmechdb.py"
    "fetch_mondo.py"
)

for script in "${EXTRACT_SCRIPTS[@]}"; do
    script_path="${SCRIPT_DIR}/etl/${script}"
    if [ -f "$script_path" ]; then
        echo -e "${YELLOW}Extracting: ${script}...${NC}"
        run_optional_step "$script" python3 "$script_path"
    else
        echo -e "${YELLOW}Skipping ${script} (not yet implemented)${NC}"
    fi
done

echo ""
echo -e "${GREEN}=== Phase 3: Normalization & Edge Generation ===${NC}"
echo ""

echo -e "${YELLOW}Normalizing drugs...${NC}"
run_optional_step "normalize_drugs" python3 "${SCRIPT_DIR}/etl/normalize_drugs.py"

echo -e "${YELLOW}Normalizing targets...${NC}"
run_optional_step "normalize_targets" python3 "${SCRIPT_DIR}/etl/normalize_targets.py"

echo -e "${YELLOW}Normalizing diseases...${NC}"
run_optional_step "normalize_diseases" python3 "${SCRIPT_DIR}/etl/normalize_diseases.py"

echo -e "${YELLOW}Generating cross-references...${NC}"
run_optional_step "generate_xrefs" python3 "${SCRIPT_DIR}/etl/generate_xrefs.py"

echo -e "${YELLOW}Generating canonical edge files...${NC}"
run_optional_step "generate_edges" python3 "${SCRIPT_DIR}/etl/generate_edges.py"

echo ""
echo -e "${GREEN}=== Phase 4: Build Artifacts ===${NC}"
echo ""

if [ -f "${PROJECT_ROOT}/scripts/build_graph_artifacts.py" ]; then
    echo -e "${GREEN}Building graph-native artifacts...${NC}"
    run_optional_step "graph artifacts" python3 "${PROJECT_ROOT}/scripts/build_graph_artifacts.py"
fi

if [ -f "${PROJECT_ROOT}/scripts/build_frontend_embeds.py" ]; then
    echo -e "${GREEN}Refreshing frontend embeds...${NC}"
    run_optional_step "frontend embeds" python3 "${PROJECT_ROOT}/scripts/build_frontend_embeds.py"
fi

echo ""

echo -e "${GREEN}=== Phase 5: SQLite Graph Loading ===${NC}"
echo ""

if [ -f "${SCRIPT_DIR}/etl/load_graph_edges.py" ]; then
    echo -e "${YELLOW}Loading graph edges into SQLite...${NC}"
    run_optional_step "SQLite loading" python3 -m src.backend.etl.load_graph_edges --db-path "${PROJECT_ROOT}/drugtree.db"
else
    echo -e "${YELLOW}Skipping SQLite loading (script not found)${NC}"
fi

echo ""
echo -e "${GREEN}ETL pipeline complete!${NC}"
echo -e "Canonical drug data: ${YELLOW}$OUTPUT_JSON${NC}"
echo -e "Processed nodes/edges: ${YELLOW}${PROJECT_ROOT}/data/processed/${NC}"
echo -e "SQLite database: ${YELLOW}${PROJECT_ROOT}/drugtree.db${NC}"
