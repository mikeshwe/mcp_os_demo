# MCP OS Demo (LP One-Pager)

An **MCP (Model Context Protocol)–based Operating System** that automatically extracts, computes, and summarizes portfolio company financial data into branded LP one-pagers using a **multi-agent non-deterministic workflow** in which agents orchestrate MCP tools via the MCP protocol, and those tools interact with different data sources (files, databases, APIs).

> 📖 **For detailed documentation, see [PRD.md](prd.md)**

---

## Quick Start

### 1. Start Database

```bash
docker compose up -d
```

Postgres URL: `postgres://mcp:mcp@localhost:5433/mcp_ctx`

### 2. Set Up Environment Variables

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Edit `.env` with your configuration:

```bash
# Database connection
DB_URL=postgres://mcp:mcp@localhost:5433/mcp_ctx

# Embedding Model (optional, default: Xenova/all-MiniLM-L6-v2 - local model, no API key needed)
EMBEDDING_MODEL=Xenova/all-MiniLM-L6-v2

# MCP Server Configuration
MCP_SERVER_URL=http://localhost:3333/mcp

# LangChain Agent Configuration (optional, for LLM content generation)
OPENAI_API_KEY=your_openai_api_key_here  # Optional - enables LLM-generated content
LLM_MODEL=gpt-3.5-turbo                  # Optional - OpenAI model to use (default: gpt-3.5-turbo)
                                         # All agents (IngestionAgent, KPIComputationAgent, ContentGenerationAgent) use this model
                                         # Supported: gpt-3.5-turbo, gpt-4, gpt-4-turbo, etc.

# Workflow Configuration (optional)
DEAL_ID=00000000-0000-0000-0000-000000000001
COMPANY_NAME=Acme Software, Inc.
PERIOD_END=2025-09-30
DATA_DIR=./data
```

**Note:** 
- Embeddings are generated using **local models** (ChromaDB) - no API key required!
- `OPENAI_API_KEY` is **optional** - only needed for LLM-generated investment thesis and risks
- If `OPENAI_API_KEY` is not set, the system will use fallback content
- `LLM_MODEL` configures the OpenAI model used by all agents (IngestionAgent, KPIComputationAgent, ContentGenerationAgent)
- Default model is `gpt-3.5-turbo`; can be changed to `gpt-4`, `gpt-4-turbo`, etc.

### 3. Start MCP Server

The server automatically loads environment variables from `.env` if it exists:

```bash
npx tsx mcp-lp-tools-server.ts
```

On first run, the embedding model will be downloaded automatically (~79MB). Subsequent runs will use the cached model.

### 4. Run Workflow

Choose your execution mode:

#### Option A: Non-Deterministic Multi-Agent Workflow (Recommended) ⭐

Intelligent agents with conditional routing, retry logic, and fallback mechanisms:

```bash
source venv/bin/activate
python demo_nondet_workflow.py
```

**Features:**
- ✅ Adaptive retry logic (up to 2 retries)
- ✅ Conditional routing based on validation results
- ✅ Fallback mechanisms for failures
- ✅ Transparent path logging

#### Option B: Deterministic Multi-Agent Workflow

Fixed-sequence multi-agent workflow with explicit state management:

```bash
source venv/bin/activate
python demo_langgraph_workflow.py
```

#### Option C: Simple Orchestrator Agent

Basic agent workflow without LangGraph:

```bash
source venv/bin/activate
python demo_agent_workflow.py
```

#### Option D: Shell Script (Legacy)

Direct MCP tool calls via shell script:

```bash
bash demo_full_workflow.sh
```

---

## 🤖 Multi-Agent Architecture

The system uses a **multi-agent architecture** powered by **LangGraph** with three specialized agents:

### Architecture Flow

```
┌─────────────────────────────────────────────────────────┐
│  Agents (Python/LangGraph)                              │
│  - IngestionAgent                                       │
│  - KPIComputationAgent                                  │
│  - ContentGenerationAgent                               │
└─────────────────────────────────────────────────────────┘
                    ↓
         (MCP protocol calls via HTTP/JSON-RPC)
                    ↓
┌─────────────────────────────────────────────────────────┐
│  MCP Server (TypeScript)                                │
│  - Exposes tools via MCP protocol                       │
│  - Session management                                   │
│  - Tool validation                                      │
└─────────────────────────────────────────────────────────┘
                    ↓
            (executes tools)
                    ↓
┌─────────────────────────────────────────────────────────┐
│  MCP Tools                                              │
│  - ingest_excel, ingest_csv, ingest_memo               │
│  - compute_kpis                                         │
│  - get_golden_facts, render_onepager_markdown          │
└─────────────────────────────────────────────────────────┘
                    ↓
         (interacts with data sources)
                    ↓
┌─────────────────────────────────────────────────────────┐
│  Data Sources                                           │
│  - Files (Excel, CSV, TXT, MD)                         │
│  - PostgreSQL Database (with pgvector)                  │
│  - APIs (future: Stripe, Zuora, Snowflake)             │
└─────────────────────────────────────────────────────────┘
```

### Agent Roles

#### 1. **IngestionAgent**
- Automatically discovers data files
- Determines optimal ingestion order (LLM-powered, configurable via `LLM_MODEL`)
- Retries failed ingestions with alternative strategies
- Validates ingestion results

#### 2. **KPIComputationAgent**
- Validates data quality before computation
- Determines optimal KPI parameters (LLM-powered, configurable via `LLM_MODEL`)
- Computes KPIs with validation
- Falls back to existing KPIs if computation fails

#### 3. **ContentGenerationAgent**
- Analyzes financial trends
- Generates investment thesis and risks using LLM (configurable via `LLM_MODEL`)
- Validates content quality
- Falls back to default content if generation fails

### Non-Deterministic Workflow

The workflow uses **conditional routing** to adapt to different conditions:

- **After Ingestion**: Routes to `continue`, `retry` (up to 2x), or `skip` based on validation
- **After KPI Computation**: Routes to `continue` or `fallback` based on results
- **After Content Generation**: Routes to `continue` or `fallback_content` based on validation

See [PRD.md](prd.md) for detailed architecture documentation.

---

## 🛠️ Installation

### Node.js Dependencies

```bash
npm install
```

### Python Dependencies

```bash
source venv/bin/activate
pip install -r requirements.txt
```

**Required Python packages:**
- `langchain`, `langchain-openai`, `langgraph` - Agent framework
- `chromadb`, `sentence-transformers` - Local embeddings
- `httpx`, `aiohttp` - HTTP client for MCP protocol
- `pg` (psycopg2-binary) - PostgreSQL client
- `python-dotenv` - Environment variable management

---

## 📖 Documentation

- **[PRD.md](prd.md)** - Complete Product Requirements Document
  - System architecture
  - Multi-agent workflow details
  - MCP protocol usage
  - Vector search & semantic retrieval
  - Tool specifications

- **[agents/README.md](agents/README.md)** - Agent implementation details
- **[NONDET_WORKFLOW.md](NONDET_WORKFLOW.md)** - Non-deterministic workflow documentation

---

## 🔍 Key Features

### Local Vector Embeddings
- Uses ChromaDB's built-in embedding model (`sentence-transformers/all-MiniLM-L6-v2`)
- No API keys required for embeddings
- Runs entirely locally (~79MB model download)

### Multi-Agent Workflow
- Specialized agents for ingestion, computation, and content generation
- LLM-powered decision-making
- Automatic retry and fallback mechanisms
- Quality validation at each step

### MCP Protocol
- Standardized JSON-RPC interface
- Session management
- Tool discovery and validation
- Streaming support

### Traceability
- Full lineage tracking from source cells to KPIs
- Expandable source links in markdown output
- Audit trail for all generated artifacts

---

## 📊 Verify Installation

Check that KPIs are computed:

```sql
SELECT k.name, kv.value, kv.unit
FROM golden_facts gf
JOIN kpi_values kv USING (kpi_value_id)
JOIN kpis k USING (kpi_id)
WHERE gf.deal_id = '00000000-0000-0000-0000-000000000001'
  AND gf.status = 'approved';
```

---

## 🚀 Example Output

The workflow generates markdown one-pagers with:
- Formatted financial metrics ($4.97 M USD, 28.4%, etc.)
- Investment thesis section with expandable sources
- Key risks & mitigants section with expandable sources
- Full lineage traceability

Example output: `data/LP_OnePager_Acme_Software_Inc_2025_09_30_nondet.md`

---

## 📁 Project Structure

```
.
├── agents/                    # Multi-agent system
│   ├── ingestion_agent.py    # Data ingestion agent
│   ├── kpi_agent.py          # KPI computation agent
│   ├── content_agent.py      # Content generation agent
│   ├── workflow_graph.py     # LangGraph workflow (deterministic)
│   └── nondet_workflow_graph.py  # LangGraph workflow (non-deterministic)
├── data/                     # Sample data files
├── scripts/                   # Utility scripts
├── sql/                       # Database schema and seeds
├── mcp-lp-tools-server.ts    # MCP server (TypeScript)
├── demo_nondet_workflow.py    # Non-deterministic workflow demo (recommended)
├── demo_langgraph_workflow.py # Deterministic workflow demo
├── demo_agent_workflow.py     # Simple orchestrator demo
├── demo_full_workflow.sh      # Shell script demo (legacy)
├── prd.md                     # Product Requirements Document
└── README.md                  # This file
```

---

## 🔧 Troubleshooting

### MCP Server Not Reachable
Ensure the server is running:
```bash
npx tsx mcp-lp-tools-server.ts
```

### OpenAI API Key Issues
- Set `OPENAI_API_KEY` in `.env` file
- Or export: `export OPENAI_API_KEY=your_key`
- If not set, system uses fallback content (still works!)
- Configure LLM model via `LLM_MODEL` env var (default: `gpt-3.5-turbo`)
- All agents use the same model configured in `LLM_MODEL`

### Import Errors
Ensure all dependencies are installed:
```bash
pip install -r requirements.txt
```

### Database Connection Issues
Ensure Docker is running and database is up:
```bash
docker compose up -d
```

---

## 📝 License

See LICENSE file for details.

---

## 🤝 Contributing

See PRD.md for architecture and design decisions.
