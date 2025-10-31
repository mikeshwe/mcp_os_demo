#!/bin/bash
# Full Demo Script: MCP LP One-Pager Generation
# Demonstrates ingestion from multiple sources, KPI computation, and rendering
# Note: Vector embeddings are automatically generated during memo ingestion (requires OPENAI_API_KEY)

set -e  # Exit on error

# Configuration
MCP_SERVER="http://localhost:3333/mcp"
DEAL_ID="00000000-0000-0000-0000-000000000001"
DEAL_NAME="Acme Software, Inc."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${SCRIPT_DIR}/data"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}MCP LP One-Pager Generation Demo${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Helper function to call MCP tool
call_mcp_tool() {
  local tool_name=$1
  local arguments=$2
  local description=$3
  
  echo -e "${YELLOW}→ ${description}${NC}"
  
  local response=$(curl -s -X POST "$MCP_SERVER" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -H "MCP-Session-Id: $SESSION_ID" \
    -d "{
      \"jsonrpc\": \"2.0\",
      \"id\": $REQUEST_ID,
      \"method\": \"tools/call\",
      \"params\": {
        \"name\": \"$tool_name\",
        \"arguments\": $arguments
      }
    }")
  
  REQUEST_ID=$((REQUEST_ID + 1))
  
  # Extract result from JSON response
  echo "$response" | python3 -c "import sys, json; data = json.load(sys.stdin); print(json.dumps(data.get('result', data), indent=2))" 2>/dev/null || echo "$response"
  echo ""
}

# Step 1: Initialize MCP Session
echo -e "${GREEN}Step 1: Initializing MCP session...${NC}"
RESPONSE=$(curl -s -i -X POST "$MCP_SERVER" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
      "protocolVersion": "2024-11-05",
      "capabilities": {},
      "clientInfo": {"name": "demo-client", "version": "1.0"}
    }
  }')

SESSION_ID=$(echo "$RESPONSE" | grep -i "^mcp-session-id:" | sed -E 's/^[^:]*: *([a-f0-9-]+).*/\1/' | tr -d '\r\n ')

if [ -z "$SESSION_ID" ]; then
  echo "❌ Error: Failed to get session ID"
  echo "Make sure the MCP server is running on $MCP_SERVER"
  echo "Start it with: DB_URL=postgres://mcp:mcp@localhost:5433/mcp_ctx npx tsx mcp-lp-tools-server.ts"
  exit 1
fi

echo -e "${GREEN}✓ Session initialized: ${SESSION_ID}${NC}"
echo ""

REQUEST_ID=2

# Step 2: Ingest Memo (Text Document)
# Note: Embeddings are generated automatically using local models (no API key needed)
echo -e "${GREEN}Step 2: Ingesting memo document...${NC}"
MEMO_FILE="${DATA_DIR}/memo_q3_2025.txt"
if [ ! -f "$MEMO_FILE" ]; then
  echo "❌ Error: Memo file not found: $MEMO_FILE"
  exit 1
fi

call_mcp_tool "ingest_memo" \
  "{
    \"deal_id\": \"$DEAL_ID\",
    \"file_path\": \"$MEMO_FILE\",
    \"chunk_size\": 1000,
    \"access_tag\": \"lp-safe\"
  }" \
  "Ingesting memo: $(basename $MEMO_FILE) (embeddings will be generated using local model)"

# Step 3: Ingest Excel File
echo -e "${GREEN}Step 3: Ingesting Excel file...${NC}"
EXCEL_FILE="${DATA_DIR}/financials_Q3_2025.xlsx"
if [ ! -f "$EXCEL_FILE" ]; then
  echo "❌ Error: Excel file not found: $EXCEL_FILE"
  echo "   Generating sample Excel file..."
  node "${SCRIPT_DIR}/scripts/generate_sample_excel.js" || {
    echo "   Failed to generate Excel file. Please create it manually."
    exit 1
  }
fi

call_mcp_tool "ingest_excel" \
  "{
    \"deal_id\": \"$DEAL_ID\",
    \"file_path\": \"$EXCEL_FILE\",
    \"sheet_hints\": [\"P&L\", \"Balance Sheet\"],
    \"version\": \"v1\"
  }" \
  "Ingesting Excel: $(basename $EXCEL_FILE) (P&L and Balance Sheet sheets)"

# Step 4: Ingest EDGAR XBRL CSV
echo -e "${GREEN}Step 4: Ingesting EDGAR XBRL data...${NC}"
EDGAR_FILE="${DATA_DIR}/edgar_xbrl_q3_2025.csv"
if [ ! -f "$EDGAR_FILE" ]; then
  echo "❌ Error: EDGAR file not found: $EDGAR_FILE"
  exit 1
fi

call_mcp_tool "ingest_edgar_xbrl" \
  "{
    \"deal_id\": \"$DEAL_ID\",
    \"file_path\": \"$EDGAR_FILE\",
    \"version\": \"v1\"
  }" \
  "Ingesting EDGAR XBRL: $(basename $EDGAR_FILE)"

# Step 5: Compute KPIs
echo -e "${GREEN}Step 5: Computing KPIs from ingested data...${NC}"
call_mcp_tool "compute_kpis" \
  "{
    \"deal_id\": \"$DEAL_ID\",
    \"periods_to_sum\": 4,
    \"approve\": true,
    \"ttl_days\": 90
  }" \
  "Computing core KPIs (Revenue_LTM, YoY_Growth, Gross_Margin, EBITDA_Margin)"

# Step 6: Get Golden Facts (Approved KPIs)
echo -e "${GREEN}Step 6: Fetching approved Golden Facts...${NC}"
GOLDEN_FACTS=$(curl -s -X POST "$MCP_SERVER" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "MCP-Session-Id: $SESSION_ID" \
  -d "{
    \"jsonrpc\": \"2.0\",
    \"id\": $REQUEST_ID,
    \"method\": \"tools/call\",
    \"params\": {
      \"name\": \"get_golden_facts\",
      \"arguments\": {
        \"deal_id\": \"$DEAL_ID\"
      }
    }
  }")

REQUEST_ID=$((REQUEST_ID + 1))

echo -e "${YELLOW}→ Fetching approved KPIs for deal${NC}"
echo "$GOLDEN_FACTS" | python3 -c "import sys, json; data = json.load(sys.stdin); result = data.get('result', {}); content = result.get('content', [{}])[0]; text = content.get('text', ''); snapshot = json.loads(text) if text else {}; print(json.dumps(snapshot, indent=2))" 2>/dev/null || echo "$GOLDEN_FACTS"
echo ""

# Step 7: Get KPI Lineage
echo -e "${GREEN}Step 7: Fetching KPI lineage (traceability)...${NC}"
call_mcp_tool "get_kpi_lineage" \
  "{
    \"deal_id\": \"$DEAL_ID\",
    \"kpis\": [\"Revenue_LTM\"]
  }" \
  "Showing source cells for Revenue_LTM KPI"

# Step 8: Render One-Pager Markdown
echo -e "${GREEN}Step 8: Rendering LP one-pager markdown...${NC}"

# Extract snapshot from golden facts
SNAPSHOT=$(echo "$GOLDEN_FACTS" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    result = data.get('result', {})
    content = result.get('content', [{}])[0]
    text = content.get('text', '')
    snapshot_data = json.loads(text) if text else {}
    # Convert to format expected by render_onepager_markdown (array format)
    snapshot = snapshot_data.get('snapshot', [])
    # Convert string values to numbers
    for item in snapshot:
        if 'value' in item and isinstance(item['value'], str):
            try:
                item['value'] = float(item['value'])
            except (ValueError, TypeError):
                pass
    print(json.dumps(snapshot))
except Exception as e:
    print('[]')
" 2>/dev/null || echo '[]')

# Call render tool and capture response
RENDER_RESPONSE=$(curl -s -X POST "$MCP_SERVER" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "MCP-Session-Id: $SESSION_ID" \
  -d "{
    \"jsonrpc\": \"2.0\",
    \"id\": $REQUEST_ID,
    \"method\": \"tools/call\",
    \"params\": {
      \"name\": \"render_onepager_markdown\",
      \"arguments\": {
        \"company\": \"$DEAL_NAME\",
        \"period_end\": \"2025-09-30\",
        \"deal_id\": \"$DEAL_ID\",
        \"snapshot\": $SNAPSHOT,
        \"bullets\": {
          \"thesis\": [
            \"Strong revenue growth trajectory with 28% YoY growth\",
            \"Market leadership position maintained with Gartner recognition\",
            \"Operational efficiency improvements driving margin expansion\"
          ],
          \"risks\": [
            \"Customer concentration (top 10 = 42% of revenue, improving)\",
            \"Competitive pressure (stable landscape, strong moat)\",
            \"Macroeconomic uncertainty (strong retention metrics provide stability)\"
          ]
        }
      }
    }
  }")

REQUEST_ID=$((REQUEST_ID + 1))

echo -e "${YELLOW}→ Generating branded LP one-pager markdown${NC}"
echo "$RENDER_RESPONSE" | python3 -c "import sys, json; data = json.load(sys.stdin); print(json.dumps(data.get('result', data), indent=2))" 2>/dev/null || echo "$RENDER_RESPONSE"
echo ""

# Extract markdown from response and save to file
OUTPUT_DIR="output"
mkdir -p "$OUTPUT_DIR"
OUTPUT_FILE="${OUTPUT_DIR}/LP_OnePager_${DEAL_NAME// /_}_Q3_2025.md"
OUTPUT_FILE="${OUTPUT_FILE//,/_}"  # Remove commas from filename
MARKDOWN=$(echo "$RENDER_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    result = data.get('result', {})
    content = result.get('content', [{}])[0]
    text = content.get('text', '')
    result_data = json.loads(text) if text else {}
    markdown = result_data.get('markdown', '')
    # Unescape markdown
    markdown = markdown.replace('\\\\n', '\n').replace('\\\\u2014', '—').replace('\\\\\"', '\"')
    print(markdown)
except Exception as e:
    print('')
" 2>/dev/null || echo '')

if [ -n "$MARKDOWN" ]; then
  echo "$MARKDOWN" > "$OUTPUT_FILE"
  echo -e "${GREEN}✓ Saved markdown to: $OUTPUT_FILE${NC}"
  echo ""
else
  echo -e "${YELLOW}⚠ Warning: Could not extract markdown from response${NC}"
  echo ""
fi

# Step 9: Register Output
echo -e "${GREEN}Step 9: Registering output artifact...${NC}"
call_mcp_tool "register_output" \
  "{
    \"deal_id\": \"$DEAL_ID\",
    \"recipe\": \"LP_OnePager_v1\",
    \"kind\": \"markdown\",
    \"uri\": \"s3://bucket/lp-onepager-acme-q3-2025.md\"
  }" \
  "Logging generated artifact with lineage"

# Summary
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✓ Demo completed successfully!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "Summary of actions:"
echo "  ✓ Ingested memo document (text chunks + local vector embeddings)"
echo "  ✓ Ingested Excel file (P&L and Balance Sheet sheets)"
echo "  ✓ Ingested EDGAR XBRL CSV (structured data)"
echo "  ✓ Computed KPIs from table cells"
echo "  ✓ Fetched approved Golden Facts"
echo "  ✓ Retrieved KPI lineage for traceability"
echo "  ✓ Rendered LP one-pager markdown (using vector search for memo sources)"
echo "  ✓ Saved markdown file to: ${OUTPUT_FILE:-output/LP_OnePager_*.md}"
echo "  ✓ Registered output artifact"
echo ""
echo -e "${YELLOW}Note:${NC} The demo uses pre-seeded data. To start fresh:"
echo "  1. Reset database: psql \$DB_URL -c 'TRUNCATE table_cells, chunks, documents CASCADE;'"
echo "  2. Run ingestion tools with actual files"
echo "  3. Embeddings are generated automatically using local models (no API key needed)"
echo "  4. For existing chunks without embeddings, run: npx tsx scripts/migrate_chunks_to_embeddings.ts"
echo ""

