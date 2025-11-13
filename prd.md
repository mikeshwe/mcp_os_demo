# Product Requirements Document (PRD)
**Project Name:** MCP OS for LP One-Pager Generation  
**Version:** v0.3.0  
**Owner:** @mike.shwe  
**Date:** October 2025  

---

## 🧭 Purpose
The goal is to create an **MCP (Model Context Protocol)–based Operating System** that automatically **extracts, computes, and summarizes portfolio company financial data** into a **branded LP one-pager** suitable for distribution to limited partners.

It enables LLM agents to securely access data, compute KPIs, and generate governed deliverables — all under version-controlled, auditable workflows using a **multi-agent non-deterministic architecture** powered by LangGraph.

---

## 🎯 Objectives

| Objective | Description |
|------------|-------------|
| **Automation** | Replace manual financial data extraction and LP memo drafting with reproducible AI workflows. |
| **Governance** | Ensure all computed KPIs and summaries are traceable to source cells / documents. |
| **Standardization** | Establish canonical schema for deals, documents, KPIs, and outputs. |
| **Scalability** | Enable portfolio-wide reporting from diverse data sources (Excel, CSV, APIs, DWs). |
| **Security & Compliance** | Enforce access tagging (LP-safe, MNPI, internal), full audit trail, and policy checks. |

---

## 🧱 System Overview

### Architecture
<img src="images/architecture.png" alt="Architecture Diagram" width="300" />

### Core Components
| Component | Description |
|------------|-------------|
| **Ingestion Tools** | Convert financial files (Excel, CSV, DW exports, memos) into structured `table_cells`, `chunks`, and `documents`. |
| **Compute Tools** | Derive KPIs (Revenue_LTM, YoY_Growth, Margins, etc.) from normalized data and write to `kpi_values` + `golden_facts`. |
| **Render Tools** | Produce branded Markdown / DOCX LP one-pagers from approved data. |
| **Register Output Tool** | Logs every generated artifact with lineage. |
| **MCP Host** | Exposes tools securely to LLMs via MCP protocol (JSON-RPC over HTTP) with session management. |
| **Multi-Agent System** | Specialized agents orchestrated via LangGraph for intelligent, adaptive workflow execution. |
| **Non-Deterministic Workflow** | Conditional routing based on validation results, retry logic, and fallback mechanisms. |

---

## ⚙️ Functional Requirements

### Ingestion Tools
| Tool | Input | Output | Notes |
|------|--------|---------|-------|
| `ingest_excel` | `.xlsx` path, sheet hints | `table_cells` rows | Detects periods, units, currency; supports multi-sheet import. |
| `ingest_csv` | `.csv` path | `table_cells` rows | Generic ERP/BI data loader. |
| `ingest_memo` | `.txt` / `.md` | `chunks` + `embeddings` | Splits memos into sections and generates vector embeddings using ChromaDB's local embedding model for semantic search. |
| `ingest_billing` | CSV of MRR movements | `table_cells` rows | Stub for future Stripe/Zuora integration. |
| `ingest_edgar_xbrl` | SEC CSV export | `table_cells` rows | Maps XBRL concepts to canonical labels. |
| `ingest_snowflake` | CSV export of DW view | `table_cells` rows | Proxy for future direct connector. |

### Compute Tools
| Tool | Name | Function |
|------|------|-----------|
| `compute_kpis` | Compute core metrics | Revenue_LTM, YoY_Growth, Gross_Margin, EBITDA_Margin. |
|  | Behavior | 1) Reads `table_cells` by label. 2) Writes to `kpi_values`. 3) Links to source `cell_id`s. 4) Promotes to `golden_facts` if approved. |

### Rendering Tools
| Tool | Name | Function |
|------|------|-----------|
| `get_golden_facts` | Fetch approved KPIs for deal | Used by LLM to draft snapshot table. |
| `get_kpi_lineage` | Fetch source lineage | For traceability and calc cards. |
| `render_onepager_markdown` | Generate Markdown one-pager | Table + narrative; themeable. Uses vector search (via ChromaDB embeddings) to find relevant memo chunks for Investment Thesis and Key Risks sections. |
| `register_output` | Log generated artifact | Creates `runs` + `outputs` DB records. |

---

## 📊 Data Model Summary

| Table | Purpose |
|--------|----------|
| `deals` | Portfolio companies. |
| `documents` | Source files ingested. |
| `tables_norm` | Logical grouping of extracted tables. |
| `table_cells` | Atomic metric values (period, label, value, unit, currency). |
| `kpis` | Canonical KPI definitions. |
| `kpi_values` | Computed KPI values with lineage. |
| `golden_facts` | Approved KPIValues used for rendering. |
| `chunks` / `embeddings` | Text fragments with vector embeddings for semantic RAG. Embeddings generated automatically during `ingest_memo` using ChromaDB's local embedding model (no API key required). |
| `runs` / `outputs` | Execution audit trail for generated artifacts. |

---

## 🔐 Non-Functional Requirements (not yet implemented)

| Category | Requirement |
|-----------|--------------|
| **Security** | Enforce read-only connectors by default; log all tool calls. |
| **Traceability** | Every numeric output linked to cell or source ref. |
| **Performance** | Generate an LP one-pager ≤ 3 minutes for 200-page corpus. |
| **Reliability** | Idempotent ingestion and computation. |
| **Scalability** | Handle ≥ 50 portfolio companies concurrently. |
| **Auditability** | Full lineage stored in DB; reproducible runs. |

---

## 🚀 User Workflow

### MCP Protocol Usage

The server exposes all tools via the **MCP (Model Context Protocol)** standard, which is optimized for LLM agent communication. All tools are accessible through JSON-RPC requests to the `/mcp` endpoint.

#### Step 1: Initialize MCP Session

```bash
# Initialize session and get session ID
RESPONSE=$(curl -s -i -X POST http://localhost:3333/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
      "protocolVersion": "2024-11-05",
      "capabilities": {},
      "clientInfo": {"name": "analyst-client", "version": "1.0"}
    }
  }')

SESSION_ID=$(echo "$RESPONSE" | grep -i "^mcp-session-id:" | sed -E 's/^[^:]*: *([a-f0-9-]+).*/\1/' | tr -d '\r\n ')
```

#### Step 2: Ingest Documents

```bash
# Ingest Excel file
curl -X POST http://localhost:3333/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "MCP-Session-Id: $SESSION_ID" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "ingest_excel",
      "arguments": {
        "deal_id": "00000000-0000-0000-0000-000000000001",
        "file_path": "/path/to/financials_Q3_2025.xlsx"
      }
    }
  }'

# Ingest CSV file
curl -X POST http://localhost:3333/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "MCP-Session-Id: $SESSION_ID" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "ingest_csv",
      "arguments": {
        "deal_id": "00000000-0000-0000-0000-000000000001",
        "file_path": "/path/to/mrr_movements.csv"
      }
    }
  }'

# Ingest memo
curl -X POST http://localhost:3333/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "MCP-Session-Id: $SESSION_ID" \
  -d '{
    "jsonrpc": "2.0",
    "id": 4,
    "method": "tools/call",
    "params": {
      "name": "ingest_memo",
      "arguments": {
        "deal_id": "00000000-0000-0000-0000-000000000001",
        "file_path": "/path/to/memo_q3.txt"
      }
    }
  }'
```

#### Step 3: Compute KPIs

```bash
curl -X POST http://localhost:3333/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "MCP-Session-Id: $SESSION_ID" \
  -d '{
    "jsonrpc": "2.0",
    "id": 5,
    "method": "tools/call",
    "params": {
      "name": "compute_kpis",
      "arguments": {
        "deal_id": "00000000-0000-0000-0000-000000000001",
        "periods_to_sum": 4,
        "approve": true,
        "ttl_days": 90
      }
    }
  }'
```

#### Step 4: Generate One-Pager

```bash
# Get approved KPIs
curl -X POST http://localhost:3333/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "MCP-Session-Id: $SESSION_ID" \
  -d '{
    "jsonrpc": "2.0",
    "id": 6,
    "method": "tools/call",
    "params": {
      "name": "get_golden_facts",
      "arguments": {
        "deal_id": "00000000-0000-0000-0000-000000000001"
      }
    }
  }'

# Render one-pager markdown
curl -X POST http://localhost:3333/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "MCP-Session-Id: $SESSION_ID" \
  -d '{
    "jsonrpc": "2.0",
    "id": 7,
    "method": "tools/call",
    "params": {
      "name": "render_onepager_markdown",
      "arguments": {
        "company": "Acme Software, Inc.",
        "period_end": "2025-09-30",
        "snapshot": [...],  // from get_golden_facts
        "bullets": {
          "thesis": ["Strong growth trajectory", "Market leadership"],
          "risks": ["Competition", "Market volatility"]
        }
      }
    }
  }'

# Register output
curl -X POST http://localhost:3333/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "MCP-Session-Id: $SESSION_ID" \
  -d '{
    "jsonrpc": "2.0",
    "id": 8,
    "method": "tools/call",
    "params": {
      "name": "register_output",
      "arguments": {
        "deal_id": "00000000-0000-0000-0000-000000000001",
        "recipe": "LP_OnePager_v1",
        "kind": "markdown",
        "uri": "s3://bucket/lp-onepager.md"
      }
    }
  }'
```

### LLM Agent Integration

LLM agents (Claude, GPT-4, etc.) can connect directly to the MCP server without manual curl commands. The MCP protocol provides:

- **Session management** - Automatic session handling
- **Streaming support** - Real-time responses via text/event-stream
- **Standardized schema** - JSON-RPC format with Zod validation
- **Tool discovery** - Automatic tool listing via `tools/list` method

### Agent-Based Execution (Recommended)

The system now includes **multi-agent workflows** that orchestrate MCP tools intelligently:

- **Automatic orchestration** - Agents coordinate tool execution
- **Intelligent decision-making** - LLM-powered choices for optimal execution
- **Error recovery** - Automatic retries and fallback mechanisms
- **Validation** - Quality checks at each step

See the [Multi-Agent Non-Deterministic Workflow](#-multi-agent-non-deterministic-workflow) section for details.

### Helper Scripts

Multiple execution modes are available:

- **`demo_nondet_workflow.py`** - Non-deterministic multi-agent workflow (recommended)

---

## 🔍 Vector Search & Semantic Retrieval

### Overview

The system uses **local vector embeddings** via **ChromaDB's built-in embedding functions** to enable semantic search for finding relevant memo chunks. This uses the `sentence-transformers/all-MiniLM-L6-v2` model that runs entirely on your machine—**no API keys or external services required**. The embeddings are stored in PostgreSQL using the pgvector extension for fast similarity search.

### How It Works

1. **Embedding Generation** (during `ingest_memo`):
   - When a memo is ingested, text chunks are automatically converted to vector embeddings
   - Uses ChromaDB's `DefaultEmbeddingFunction()` which employs the `sentence-transformers/all-MiniLM-L6-v2` model
   - Embeddings are generated via a Python script (`scripts/generate_embeddings_python.py`) called from the TypeScript server
   - Embeddings are stored in the `embeddings` table with `VECTOR(384)` type (384 dimensions)
   - Runs entirely locally using ChromaDB - no API calls or external dependencies

2. **Vector Search** (during `render_onepager_markdown`):
   - When rendering a one-pager, the system generates query embeddings for "Investment Thesis" and "Key Risks"
   - Uses PostgreSQL's pgvector extension to find semantically similar chunks
   - Returns top 3 most relevant chunks based on cosine similarity

3. **Fallback Strategy**:
   - If embeddings are not available, falls back to rule-based matching
   - Rule-based matching uses section name keywords as before
   - Ensures system works even if embedding generation fails

### Setup Requirements

**No API Keys Required!** The system uses ChromaDB's local embedding models.

**Python Dependencies:**
```bash
# Install ChromaDB in the virtual environment
source venv/bin/activate
pip install chromadb sentence-transformers
```

**Environment Variables:**
```bash
DB_URL=postgres://mcp:mcp@localhost:5433/mcp_ctx  # Database connection
EMBEDDING_MODEL=Xenova/all-MiniLM-L6-v2          # Optional (used for fallback only)
```

**Database:**
- PostgreSQL with pgvector extension (already configured in `docker-compose.yml`)
- `embeddings` table with `VECTOR(384)` column (already in schema)

**Model Download:**
- On first run, ChromaDB will download the `all-MiniLM-L6-v2` model (~79MB)
- Model is cached locally in `~/.cache/chroma/onnx_models/`
- Subsequent runs use the cached model

### Architecture

The embedding generation uses a hybrid approach:

1. **TypeScript Server** (`mcp-lp-tools-server.ts`):
   - Calls Python script via `child_process.exec()`
   - Passes text chunks as base64-encoded arguments (to avoid shell injection)
   - Receives JSON array of embeddings

2. **Python Script** (`scripts/generate_embeddings_python.py`):
   - Uses ChromaDB's `DefaultEmbeddingFunction()`
   - Handles model loading and caching automatically
   - Converts numpy arrays to JSON-serializable lists
   - Returns embeddings as JSON array

3. **Database Storage**:
   - Embeddings stored in PostgreSQL `embeddings` table
   - Uses pgvector extension for similarity search
   - Vector dimension: 384 (all-MiniLM-L6-v2)

### Migration

For existing chunks without embeddings, run the migration script:

```bash
DB_URL=postgres://mcp:mcp@localhost:5433/mcp_ctx \
npx tsx scripts/migrate_chunks_to_embeddings.ts
```

**Note:** The migration script has been updated to use ChromaDB via Python instead of OpenAI.

### Performance

- **Embedding Generation**: ~100-200ms per chunk (local CPU processing via ChromaDB)
- **Vector Search**: <10ms per query (with pgvector index)
- **Cost**: Free! No API costs, runs entirely locally
- **Model Size**: ~79MB (downloaded once, cached locally)

### Query Templates

The system uses predefined query templates for semantic search:

- **Investment Thesis**: "Investment thesis: strong revenue growth, market leadership, competitive advantages, business performance, financial outlook..."
- **Key Risks**: "Key risks and mitigants: competitive pressure, customer concentration, macroeconomic uncertainty, operational risks..."

These templates are combined and used to generate query embeddings that find semantically similar content in memo chunks.

---

## 🤖 Multi-Agent Non-Deterministic Workflow

### Overview

The system uses a **multi-agent architecture** powered by **LangGraph** to orchestrate the LP one-pager generation workflow. Unlike traditional scripted workflows, this system makes intelligent decisions and adapts to conditions dynamically through conditional routing, retry logic, and fallback mechanisms.

### Architecture

```
┌─────────────────────────────────────────────────┐
│         LangGraph Workflow                      │
│  (Non-Deterministic State Management)           │
└─────────────────────────────────────────────────┘
                    │
        ┌───────────┼───────────┐
        │           │           │
┌───────▼──────┐ ┌──▼──────┐ ┌──▼──────────────┐
│ Ingestion   │ │ KPI     │ │ Content         │
│ Agent       │ │ Agent   │ │ Generation      │
│             │ │         │ │ Agent           │
│ - Discover │ │ - Valid │ │ - Analyze       │
│ - Ingest    │ │ - Compute│ │ - Generate     │
│ - Validate  │ │ - Validate│ │ - Validate    │
│ - Retry     │ │ - Fallback│ │ - Fallback    │
└─────────────┘ └─────────┘ └─────────────────┘
```

### Agent Roles

#### 1. **IngestionAgent**
- **Responsibilities**:
  - Automatically discovers available data files
  - Determines optimal ingestion order (LLM-powered or rule-based)
  - Executes ingestion with intelligent retry logic
  - Validates ingestion results and provides recommendations

- **Features**:
  - LLM determines optimal ingestion strategy based on file types and content
  - LLM model configurable via `LLM_MODEL` environment variable (default: `gpt-3.5-turbo`)
  - Retries failed ingestions with alternative parameters (up to 2 retries)
  - Validates that required file types are ingested
  - Provides warnings and recommendations for missing data

#### 2. **KPIComputationAgent**
- **Responsibilities**:
  - Validates data quality before computation
  - Determines optimal KPI computation parameters (LLM-powered)
  - Computes KPIs from ingested data
  - Validates computed KPIs against requirements

- **Features**:
  - Checks data availability before computation
  - LLM determines optimal parameters (periods_to_sum, approve, ttl_days)
  - LLM model configurable via `LLM_MODEL` environment variable (default: `gpt-3.5-turbo`)
  - Validates that required KPIs are computed
  - Falls back to existing KPIs if computation fails

#### 3. **ContentGenerationAgent**
- **Responsibilities**:
  - Analyzes financial trends from snapshot data
  - Generates investment thesis bullets using LLM
  - Generates key risks with mitigants using LLM
  - Validates content quality

- **Features**:
  - Analyzes financial trends (revenue growth, margin trends, key metrics)
  - Generates data-driven, contextually relevant content
  - LLM model configurable via `LLM_MODEL` environment variable (default: `gpt-3.5-turbo`)
  - Validates content completeness (thesis and risks bullets)
  - Falls back to default content if generation fails

### Non-Deterministic Workflow

The workflow uses **conditional routing** with `add_conditional_edges()` to adapt to different conditions:

#### Decision Points

1. **After Ingestion** → Routes to:
   - `continue`: Validation passed, proceed to KPI computation
   - `retry`: Validation failed, retry with alternative strategy (up to 2 times)
   - `skip`: Max retries reached, continue with warnings

2. **After KPI Computation** → Routes to:
   - `continue`: KPIs computed successfully, proceed to snapshot
   - `fallback`: No KPIs computed, use existing KPIs from database

3. **After Content Generation** → Routes to:
   - `continue`: Content validated successfully, proceed to render
   - `fallback_content`: Content generation failed, use fallback content

#### Workflow Graph

```
initialize
    ↓
ingestion ──┐
    ↓       │
  [validate]│
    ├─ continue → kpi_computation
    ├─ retry ────┘ (up to 2 retries)
    └─ skip ──────→ kpi_computation (with warnings)
    
kpi_computation ──┐
    ↓              │
  [validate]       │
    ├─ continue → get_snapshot
    └─ fallback ───┘ (use_existing_kpis)
    
get_snapshot
    ↓
content_generation ──┐
    ↓                 │
  [validate]          │
    ├─ continue → render
    └─ fallback_content ─┘ (use_fallback_content)
    
render → save_output → register_output → finalize
```

### Benefits

1. **Adaptive Behavior**: Workflow adapts to failures and retries intelligently
2. **Resilience**: Fallback mechanisms ensure workflow completes even with partial failures
3. **Transparency**: Clear logging shows which path was taken and why
4. **Intelligence**: LLM-powered decision-making for optimal execution
5. **Debugging**: Easy to trace execution path through conditional branches

### Implementation

The workflow is implemented using:
- **LangGraph**: Explicit state management and conditional routing
- **LangChain**: LLM integration for intelligent decision-making
- **Python Agents**: Specialized agent classes for each domain
- **MCP Tools**: Underlying tools exposed via MCP protocol

### LLM Configuration

All agents use a **configurable LLM model** via the `LLM_MODEL` environment variable:
- **Default**: `gpt-3.5-turbo`
- **Configurable**: Set `LLM_MODEL` in `.env` file (e.g., `LLM_MODEL=gpt-4`)
- **Consistency**: All agents (IngestionAgent, KPIComputationAgent, ContentGenerationAgent) use the same model
- **Fallback**: If `OPENAI_API_KEY` is not set, agents use rule-based fallback strategies instead of LLM calls

### Usage

#### Run Non-Deterministic Workflow (Recommended):
```bash
source venv/bin/activate
python demo_nondet_workflow.py
```


### State Management

The workflow uses a `WorkflowState` TypedDict that tracks:
- Input parameters (deal_id, company_name, period_end, data_dir)
- MCP session state (mcp_caller, session_id)
- Step results (discovered_files, ingestion_results, kpi_results, snapshot, bullets, markdown)
- Error handling (errors list, retry_count)
- Final summary (success, summary dict)

Errors are accumulated across the workflow using `Annotated[List[str], lambda x, y: x + y]` to track all warnings and failures.

### Example Execution

```
✓ MCP session initialized
📥 Ingestion Agent (Attempt 1)
  ✓ Ingested files...
  ⚠ Ingestion validation failed - routing to RETRY

🔄 Retrying ingestion with alternative strategy (Retry 1)
  ✓ Ingested files...
  ⚠ Ingestion validation failed - routing to RETRY

🔄 Retrying ingestion with alternative strategy (Retry 2)
  ⚠ Max retries reached - routing to SKIP (with warnings)

📊 KPI Computation Agent
  ✓ Computed KPIs: 4 KPIs created
  ✓ KPI validation passed - routing to CONTINUE

📋 Retrieving Golden Facts Snapshot
  ✓ Retrieved 168 approved KPIs

✍️ Content Generation Agent
  ✓ Generated 5 thesis bullets and 5 risks
  ✓ Content validation passed - routing to CONTINUE

🎨 Rendering One-Pager
  ✓ Generated one-pager markdown

Summary:
  Path Taken: non-deterministic
  Retry Count: 2
  Success: True
```

This demonstrates how the workflow adapts to conditions, retries operations, and completes successfully despite partial failures.
