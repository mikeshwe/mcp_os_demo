"""
Demo script using LangGraph multi-agent workflow
"""

import asyncio
import os
import sys
from dotenv import load_dotenv
from agents.workflow_graph import create_workflow_app
from agents.graph_state import WorkflowState

# Load environment variables
load_dotenv()

async def main():
    # Configuration
    MCP_SERVER = os.getenv("MCP_SERVER_URL", "http://localhost:3333/mcp")
    DEAL_ID = os.getenv("DEAL_ID", "00000000-0000-0000-0000-000000000001")
    COMPANY_NAME = os.getenv("COMPANY_NAME", "Acme Software, Inc.")
    PERIOD_END = os.getenv("PERIOD_END", "2025-09-30")
    DATA_DIR = os.getenv("DATA_DIR", "./data")
    
    # Check if MCP server is running
    import httpx
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            await client.get(MCP_SERVER.replace("/mcp", ""))
    except:
        print(f"❌ Error: MCP server not reachable at {MCP_SERVER}")
        print("   Start the server with: DB_URL=postgres://mcp:mcp@localhost:5433/mcp_ctx npx tsx mcp-lp-tools-server.ts")
        sys.exit(1)
    
    # Create workflow app
    app = create_workflow_app(mcp_server_url=MCP_SERVER)
    
    # Get LLM model from environment
    LLM_MODEL = os.getenv("LLM_MODEL", "gpt-3.5-turbo")
    
    # Initialize state
    initial_state: WorkflowState = {
        "deal_id": DEAL_ID,
        "company_name": COMPANY_NAME,
        "period_end": PERIOD_END,
        "data_dir": DATA_DIR,
        "mcp_server_url": MCP_SERVER,
        "mcp_caller": None,
        "session_id": None,
        "llm_model": LLM_MODEL,
        "discovered_files": {},
        "ingestion_results": {},
        "kpi_results": {},
        "snapshot": [],
        "bullets": {},
        "markdown": "",
        "output_file": None,
        "errors": [],
        "retry_count": 0,
        "success": False,
        "summary": {}
    }
    
    print("\n" + "="*50)
    print("LP One-Pager Generation - LangGraph Multi-Agent Workflow")
    print("="*50 + "\n")
    
    try:
        # Run workflow
        result = await app.ainvoke(initial_state)
        
        # Print summary
        summary = result.get("summary", {})
        print("\n" + "="*50)
        print("Summary:")
        print("="*50)
        print(f"  Success: {summary.get('success', False)}")
        print(f"  Files ingested: {summary.get('files_ingested', 0)}")
        print(f"  KPIs computed: {summary.get('kpis_computed', 0)}")
        print(f"  Snapshot size: {summary.get('snapshot_size', 0)} KPIs")
        print(f"  Content generated: {summary.get('bullets_generated', 0)} bullets")
        print(f"  Output file: {summary.get('output_file', 'N/A')}")
        
        errors = summary.get("errors", [])
        if errors:
            print(f"\n  Errors/Warnings ({len(errors)}):")
            for error in errors[:5]:  # Show first 5
                print(f"    - {error}")
        
        print("="*50 + "\n")
        
        if not summary.get("success", False):
            sys.exit(1)
        
    except Exception as e:
        print(f"\n❌ Workflow failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())

