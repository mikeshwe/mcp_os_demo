"""
Demo script using LangGraph multi-agent workflow
Demonstrates conditional routing and decision-making with specialized agents
"""

import asyncio
import argparse
import os
import sys
import uuid
from dotenv import load_dotenv
from agents.nondet_workflow_graph import create_non_deterministic_workflow_app
from agents.graph_state import WorkflowState

# Load environment variables
load_dotenv()

async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="LP One-Pager Generation - Multi-Agent LangGraph Workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Standard mode (hardcoded tool selection)
  python demo_agent_workflow.py
  
  # Discovery mode (agents query MCP server for tools and use LLM to select)
  python demo_agent_workflow.py --discover-tools
        """
    )
    parser.add_argument(
        "--discover-tools",
        action="store_true",
        help="Enable dynamic tool discovery: agents query MCP server for available tools "
             "and their schemas, then use LLM reasoning to select the appropriate tool"
    )
    args = parser.parse_args()
    # Configuration
    MCP_SERVER = os.getenv("MCP_SERVER_URL", "http://localhost:3333/mcp")
    DEAL_ID = os.getenv("DEAL_ID", "00000000-0000-0000-0000-000000000001")
    COMPANY_NAME = os.getenv("COMPANY_NAME", "Acme Software, Inc.")
    PERIOD_END = os.getenv("PERIOD_END", "2025-09-30")
    DATA_DIR = os.getenv("DATA_DIR", "./data")
    SESSION_LABEL = os.getenv("SESSION_LABEL", f"{COMPANY_NAME} {PERIOD_END}")
    
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
    app = create_non_deterministic_workflow_app(mcp_server_url=MCP_SERVER)
    
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
        "session_label": SESSION_LABEL,
        "run_id": None,
        "llm_model": LLM_MODEL,
        "use_tool_discovery": args.discover_tools,
        "discovered_files": {},
        "ingestion_results": {},
        "ingestion_validation": {},
        "kpi_results": {},
        "kpi_validation": {},
        "snapshot": [],
        "bullets": {},
        "content_validation": {},
        "markdown": "",
        "output_file": None,
        "errors": [],
        "retry_count": 0,
        "success": False,
        "summary": {}
    }
    
    print("\n" + "="*70)
    print("LP One-Pager Generation - Multi-Agent LangGraph Workflow")
    print("="*70)
    if args.discover_tools:
        print("🔍 Tool Discovery Mode: ENABLED")
        print("   Agents will query MCP server for available tools and use LLM reasoning")
    else:
        print("📋 Tool Selection Mode: Hardcoded")
        print("   Agents use predefined logic to select tools")
    print("\nThis workflow demonstrates conditional routing based on:")
    print("  • Ingestion validation results → RETRY or CONTINUE")
    print("  • KPI validation results → FALLBACK or CONTINUE")
    print("  • Content validation results → FALLBACK_CONTENT or CONTINUE")
    print("="*70 + "\n")
    
    try:
        # Run workflow
        result = await app.ainvoke(initial_state)
        
        # Print summary
        summary = result.get("summary", {})
        print("\n" + "="*70)
        print("Workflow Summary:")
        print("="*70)
        print(f"  Success: {summary.get('success', False)}")
        print(f"  Path Taken: {summary.get('path_taken', 'unknown')}")
        print(f"  Retry Count: {summary.get('retry_count', 0)}")
        print(f"  Files ingested: {summary.get('files_ingested', 0)}")
        print(f"  KPIs computed: {summary.get('kpis_computed', 0)}")
        print(f"  Snapshot size: {summary.get('snapshot_size', 0)} KPIs")
        print(f"  Content generated: {summary.get('bullets_generated', 0)} bullets")
        print(f"  Output file: {summary.get('output_file', 'N/A')}")
        print(f"  Session: {summary.get('session_label', summary.get('session_id'))}")
        print(f"  Run ID: {summary.get('run_id', 'N/A')}")
        
        errors = summary.get("errors", [])
        if errors:
            print(f"\n  Errors/Warnings ({len(errors)}):")
            for error in errors[:5]:  # Show first 5
                print(f"    - {error}")
        
        print("="*70 + "\n")
        
        # Show workflow path taken
        print("Workflow Path Visualization:")
        print("  initialize → ingestion")
        if summary.get("retry_count", 0) > 0:
            print(f"    └─ retry_ingestion (×{summary.get('retry_count', 0)})")
        print("    └─ kpi_computation")
        if summary.get("kpis_computed", 0) == 0:
            print("      └─ use_existing_kpis (fallback)")
        print("    └─ get_snapshot")
        print("    └─ content_generation")
        bullets_count = summary.get("bullets_generated", 0)
        if bullets_count == 0:
            print("      └─ use_fallback_content (fallback)")
        print("    └─ render → save_output → register_output → finalize")
        print("")
        
        if not summary.get("success", False):
            sys.exit(1)
        
    except Exception as e:
        print(f"\n❌ Workflow failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
