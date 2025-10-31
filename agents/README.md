# Agent-Based LP One-Pager Generation

This directory contains LangChain-based agents that automate the LP one-pager generation workflow.

## Architecture

- **`mcp_tools.py`**: MCP tool wrapper for LangChain
  - `McpToolCaller`: Handles HTTP communication with MCP server
  - `McpTool`: LangChain-compatible tool wrapper
  - `create_mcp_tools()`: Factory function to create all MCP tools

- **`orchestrator.py`**: Main orchestrator agent
  - `OrchestratorAgent`: Coordinates the complete workflow
  - Handles data ingestion, KPI computation, content generation, and rendering

## Quick Start

### 1. Install Dependencies

```bash
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Set Environment Variables

Create a `.env` file (or use `.env.example` as template):

```bash
DB_URL=postgres://mcp:mcp@localhost:5433/mcp_ctx
OPENAI_API_KEY=your_openai_api_key_here  # Required for LLM content generation
MCP_SERVER_URL=http://localhost:3333/mcp
DEAL_ID=00000000-0000-0000-0000-000000000001
COMPANY_NAME=Acme Software, Inc.
PERIOD_END=2025-09-30
DATA_DIR=./data
```

### 3. Start MCP Server

```bash
DB_URL=postgres://mcp:mcp@localhost:5433/mcp_ctx npx tsx mcp-lp-tools-server.ts
```

### 4. Run Agent Demo

```bash
source venv/bin/activate
python demo_agent_workflow.py
```

## Workflow

The orchestrator agent executes the following steps:

1. **Initialize MCP Session**: Establishes connection to MCP server
2. **Discover & Ingest Data**: Automatically finds and ingests Excel, CSV, and memo files
3. **Compute KPIs**: Calculates financial KPIs from ingested data
4. **Get Snapshot**: Retrieves approved Golden Facts
5. **Generate Content**: Uses LLM to generate investment thesis and risks
6. **Render One-Pager**: Generates markdown output with lineage
7. **Save & Register**: Saves output file and registers artifact

## Agent Capabilities

### Intelligent Data Discovery
- Automatically detects available files in `/data` directory
- Selects appropriate ingestion tools based on file type
- Handles missing files gracefully

### Error Handling
- Retries failed operations
- Provides detailed error messages
- Continues workflow even if some steps fail

### Content Generation
- Uses GPT-4 to analyze financial data
- Generates contextually relevant investment thesis
- Identifies key risks with mitigants

## Future Enhancements

- **Multi-Agent System**: Separate agents for ingestion, computation, and generation
- **LangGraph Integration**: Explicit state management and workflow graphs
- **Quality Validation**: Agent validates data quality before processing
- **Human-in-the-Loop**: Request approvals for critical operations
- **LangSmith Monitoring**: Detailed observability and debugging

## Troubleshooting

### MCP Server Not Reachable
Ensure the MCP server is running:
```bash
DB_URL=postgres://mcp:mcp@localhost:5433/mcp_ctx npx tsx mcp-lp-tools-server.ts
```

### OpenAI API Key Missing
Set `OPENAI_API_KEY` in `.env` file or export as environment variable.

### Import Errors
Ensure all dependencies are installed:
```bash
pip install -r requirements.txt
```
