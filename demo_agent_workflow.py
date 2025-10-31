"""
Demo script using LangChain agents for LP one-pager generation
"""

import asyncio
import os
import sys
from dotenv import load_dotenv
from agents.orchestrator import OrchestratorAgent

# Load environment variables
load_dotenv()

async def main():
    # Configuration
    MCP_SERVER = os.getenv("MCP_SERVER_URL", "http://localhost:3333/mcp")
    DEAL_ID = os.getenv("DEAL_ID", "00000000-0000-0000-0000-000000000001")
    COMPANY_NAME = os.getenv("COMPANY_NAME", "Acme Software, Inc.")
    PERIOD_END = os.getenv("PERIOD_END", "2025-09-30")
    DATA_DIR = os.getenv("DATA_DIR", "./data")
    LLM_MODEL = os.getenv("LLM_MODEL", "gpt-3.5-turbo")  # Configurable model
    
    # Check if MCP server is running
    import httpx
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            await client.get(MCP_SERVER.replace("/mcp", ""))
    except:
        print(f"❌ Error: MCP server not reachable at {MCP_SERVER}")
        print("   Start the server with: DB_URL=postgres://mcp:mcp@localhost:5433/mcp_ctx npx tsx mcp-lp-tools-server.ts")
        sys.exit(1)
    
    # Create and run orchestrator agent
    # Model can be configured via LLM_MODEL env var (e.g., gpt-4, gpt-3.5-turbo, etc.)
    agent = OrchestratorAgent(mcp_server_url=MCP_SERVER, model=LLM_MODEL)
    
    try:
        result = await agent.run_workflow(
            deal_id=DEAL_ID,
            company_name=COMPANY_NAME,
            period_end=PERIOD_END,
            data_dir=DATA_DIR
        )
        
        print("\n" + "="*50)
        print("Summary:")
        print("="*50)
        print(f"  Files ingested: {len(result['ingestion_results']['ingested'])}")
        print(f"  KPIs computed: {result['kpis_computed']}")
        print(f"  Snapshot size: {result['snapshot_size']} KPIs")
        print(f"  Content generated: {result['bullets_generated']} bullets")
        print(f"  Output file: {result['output_file']}")
        print("="*50 + "\n")
        
    except Exception as e:
        print(f"\n❌ Workflow failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())

