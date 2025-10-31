"""
Orchestrator Agent - Coordinates the LP one-pager generation workflow
"""

import asyncio
import os
from typing import Dict, Any, Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from agents.mcp_tools import McpToolCaller, create_mcp_tools


class OrchestratorAgent:
    """Main orchestrator agent that coordinates the LP one-pager generation workflow"""
    
    def __init__(self, mcp_server_url: str = "http://localhost:3333/mcp", model: str = "gpt-3.5-turbo"):
        self.mcp_server_url = mcp_server_url
        self.model = model
        self.llm = None
        self.mcp_caller: Optional[McpToolCaller] = None
        self.tools: list = []
        
        # Initialize LLM only if API key is available
        try:
            import os
            if os.getenv("OPENAI_API_KEY"):
                self.llm = ChatOpenAI(model=model, temperature=0)
        except Exception:
            pass  # LLM will use fallback content
    
    async def initialize(self):
        """Initialize MCP session and load tools"""
        self.mcp_caller = McpToolCaller(self.mcp_server_url, "")
        session_id = await self.mcp_caller.initialize_session("langchain-orchestrator")
        print(f"✓ MCP session initialized: {session_id}")
        
        self.tools = create_mcp_tools(self.mcp_caller)
        print(f"✓ Loaded {len(self.tools)} MCP tools")
    
    async def discover_files(self, data_dir: str) -> Dict[str, list]:
        """Discover available data files in the data directory"""
        files = {
            "excel": [],
            "csv": [],
            "memo": [],
        }
        
        if not os.path.exists(data_dir):
            return files
        
        for filename in os.listdir(data_dir):
            filepath = os.path.join(data_dir, filename)
            if os.path.isfile(filepath):
                if filename.endswith('.xlsx'):
                    files["excel"].append(filepath)
                elif filename.endswith('.csv'):
                    files["csv"].append(filepath)
                elif filename.endswith(('.txt', '.md')):
                    files["memo"].append(filepath)
        
        return files
    
    async def ingest_data(self, deal_id: str, data_dir: str) -> Dict[str, Any]:
        """Intelligently ingest all available data sources"""
        files = await self.discover_files(data_dir)
        results = {
            "ingested": [],
            "skipped": [],
            "errors": []
        }
        
        # Ingest memo files
        for memo_file in files["memo"]:
            try:
                result = await self.mcp_caller.call_tool("ingest_memo", {
                    "deal_id": deal_id,
                    "file_path": memo_file,
                    "chunk_size": 1000,
                    "access_tag": "lp-safe"
                })
                results["ingested"].append({"type": "memo", "file": memo_file, "result": result})
                print(f"✓ Ingested memo: {os.path.basename(memo_file)}")
            except Exception as e:
                results["errors"].append({"type": "memo", "file": memo_file, "error": str(e)})
                print(f"✗ Failed to ingest memo {memo_file}: {e}")
        
        # Ingest Excel files
        for excel_file in files["excel"]:
            try:
                result = await self.mcp_caller.call_tool("ingest_excel", {
                    "deal_id": deal_id,
                    "file_path": excel_file,
                    "sheet_hints": ["P&L", "Balance Sheet"],
                    "version": "v1"
                })
                results["ingested"].append({"type": "excel", "file": excel_file, "result": result})
                print(f"✓ Ingested Excel: {os.path.basename(excel_file)}")
            except Exception as e:
                results["errors"].append({"type": "excel", "file": excel_file, "error": str(e)})
                print(f"✗ Failed to ingest Excel {excel_file}: {e}")
        
        # Ingest CSV files (prioritize EDGAR XBRL)
        for csv_file in files["csv"]:
            try:
                # Check if it's EDGAR XBRL format
                if "edgar" in csv_file.lower() or "xbrl" in csv_file.lower():
                    result = await self.mcp_caller.call_tool("ingest_edgar_xbrl", {
                        "deal_id": deal_id,
                        "file_path": csv_file,
                        "version": "v1"
                    })
                else:
                    result = await self.mcp_caller.call_tool("ingest_csv", {
                        "deal_id": deal_id,
                        "file_path": csv_file,
                        "version": "v1"
                    })
                results["ingested"].append({"type": "csv", "file": csv_file, "result": result})
                print(f"✓ Ingested CSV: {os.path.basename(csv_file)}")
            except Exception as e:
                results["errors"].append({"type": "csv", "file": csv_file, "error": str(e)})
                print(f"✗ Failed to ingest CSV {csv_file}: {e}")
        
        return results
    
    async def compute_kpis(self, deal_id: str) -> Dict[str, Any]:
        """Compute KPIs from ingested data"""
        try:
            result = await self.mcp_caller.call_tool("compute_kpis", {
                "deal_id": deal_id,
                "periods_to_sum": 4,
                "approve": True,
                "ttl_days": 90
            })
            print(f"✓ Computed KPIs: {len(result.get('created', []))} KPIs created")
            return result
        except Exception as e:
            print(f"✗ Failed to compute KPIs: {e}")
            raise
    
    async def get_snapshot(self, deal_id: str) -> list:
        """Get approved Golden Facts snapshot"""
        try:
            result = await self.mcp_caller.call_tool("get_golden_facts", {
                "deal_id": deal_id
            })
            
            # Handle MCP response format: result.content[0].text contains JSON
            if isinstance(result, dict):
                if "snapshot" in result:
                    snapshot = result["snapshot"]
                elif "content" in result:
                    # MCP response format
                    content = result.get("content", [])
                    if content and len(content) > 0:
                        text = content[0].get("text", "")
                        if text:
                            import json
                            snapshot_data = json.loads(text)
                            snapshot = snapshot_data.get("snapshot", [])
                        else:
                            snapshot = []
                    else:
                        snapshot = []
                else:
                    snapshot = []
            else:
                snapshot = []
            
            # Ensure snapshot items have correct format (convert string values to numbers)
            for item in snapshot:
                if isinstance(item, dict) and "value" in item:
                    if isinstance(item["value"], str):
                        try:
                            item["value"] = float(item["value"])
                        except (ValueError, TypeError):
                            pass
            
            print(f"✓ Retrieved {len(snapshot)} approved KPIs")
            return snapshot
        except Exception as e:
            print(f"✗ Failed to get snapshot: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    async def generate_content(self, deal_id: str, snapshot: list) -> Dict[str, list]:
        """Generate investment thesis and risks using LLM"""
        # If LLM is not available, use fallback content
        if not self.llm:
            print("⚠ OpenAI API key not set - using fallback content")
            return {
                "thesis": [
                    "Strong revenue growth trajectory with expanding market share",
                    "Market leadership position maintained with strong competitive moat",
                    "Operational efficiency improvements driving margin expansion"
                ],
                "risks": [
                    "Customer concentration risk (mitigated by diversification efforts)",
                    "Competitive pressure in core markets (stable landscape, strong moat)",
                    "Macroeconomic uncertainty (strong retention metrics provide stability)"
                ]
            }
        
        # Format snapshot for LLM
        snapshot_text = "\n".join([
            f"- {item['kpi']}: {item['value']} {item.get('unit', '')}"
            for item in snapshot[:10]  # Limit to first 10 KPIs
        ])
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a financial analyst generating content for LP one-pagers.
            Analyze the financial snapshot and generate:
            1. 3-5 investment thesis bullets highlighting strengths and opportunities
            2. 3-5 key risks with mitigants
            
            Be specific, data-driven, and professional."""),
            ("human", """Financial Snapshot:
{snapshot}

Generate investment thesis and risks as JSON:
{{
  "thesis": ["bullet 1", "bullet 2", ...],
  "risks": ["risk 1", "risk 2", ...]
}}""")
        ])
        
        parser = JsonOutputParser()
        chain = prompt | self.llm | parser
        
        try:
            result = await chain.ainvoke({"snapshot": snapshot_text})
            print(f"✓ Generated {len(result.get('thesis', []))} thesis bullets and {len(result.get('risks', []))} risks")
            return result
        except Exception as e:
            print(f"✗ Failed to generate content with LLM: {e}")
            # Fallback to default content
            return {
                "thesis": ["Strong revenue growth trajectory", "Market leadership position", "Operational efficiency improvements"],
                "risks": ["Customer concentration", "Competitive pressure", "Macroeconomic uncertainty"]
            }
    
    async def render_onepager(self, deal_id: str, company: str, period_end: str, snapshot: list, bullets: Dict[str, list]) -> str:
        """Render the LP one-pager markdown"""
        try:
            result = await self.mcp_caller.call_tool("render_onepager_markdown", {
                "company": company,
                "period_end": period_end,
                "snapshot": snapshot,
                "bullets": bullets,
                "deal_id": deal_id
            })
            
            # Handle MCP response format
            if isinstance(result, dict):
                if "markdown" in result:
                    markdown = result["markdown"]
                elif "content" in result:
                    # MCP response format
                    content = result.get("content", [])
                    if content and len(content) > 0:
                        text = content[0].get("text", "")
                        if text:
                            import json
                            result_data = json.loads(text)
                            markdown = result_data.get("markdown", "")
                        else:
                            markdown = ""
                    else:
                        markdown = ""
                else:
                    markdown = ""
            else:
                markdown = str(result)
            
            # Unescape markdown if needed
            markdown = markdown.replace('\\n', '\n').replace('\\u2014', '—').replace('\\"', '"')
            
            print(f"✓ Generated one-pager markdown ({len(markdown)} chars)")
            return markdown
        except Exception as e:
            print(f"✗ Failed to render one-pager: {e}")
            raise
    
    async def run_workflow(
        self,
        deal_id: str,
        company_name: str,
        period_end: str,
        data_dir: str = "./data",
        output_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """Run the complete LP one-pager generation workflow"""
        
        print("\n" + "="*50)
        print("LP One-Pager Generation - Agent Workflow")
        print("="*50 + "\n")
        
        # Step 1: Initialize
        await self.initialize()
        
        # Step 2: Ingest data
        print("\n[Step 1] Ingesting data sources...")
        ingestion_results = await self.ingest_data(deal_id, data_dir)
        
        # Step 3: Compute KPIs
        print("\n[Step 2] Computing KPIs...")
        kpi_result = await self.compute_kpis(deal_id)
        
        # Step 4: Get snapshot
        print("\n[Step 3] Fetching approved Golden Facts...")
        snapshot = await self.get_snapshot(deal_id)
        
        # Step 5: Generate content
        print("\n[Step 4] Generating investment thesis and risks...")
        bullets = await self.generate_content(deal_id, snapshot)
        
        # Step 6: Render one-pager
        print("\n[Step 5] Rendering LP one-pager...")
        markdown = await self.render_onepager(deal_id, company_name, period_end, snapshot, bullets)
        
        # Step 7: Save output
        if not output_file:
            safe_name = company_name.replace(" ", "_").replace(",", "").replace(".", "")
            output_file = f"{data_dir}/LP_OnePager_{safe_name}_{period_end.replace('-', '_')}.md"
        
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w') as f:
            f.write(markdown)
        
        print(f"\n✓ Saved one-pager to: {output_file}")
        
        # Step 8: Register output
        print("\n[Step 6] Registering output artifact...")
        try:
            await self.mcp_caller.call_tool("register_output", {
                "deal_id": deal_id,
                "recipe": "LP_OnePager_v1",
                "kind": "markdown",
                "uri": f"file://{os.path.abspath(output_file)}"
            })
            print("✓ Output registered")
        except Exception as e:
            print(f"⚠ Failed to register output: {e}")
        
        print("\n" + "="*50)
        print("✓ Workflow completed successfully!")
        print("="*50 + "\n")
        
        return {
            "success": True,
            "output_file": output_file,
            "ingestion_results": ingestion_results,
            "kpis_computed": len(kpi_result.get("created", [])),
            "snapshot_size": len(snapshot),
            "bullets_generated": len(bullets.get("thesis", [])) + len(bullets.get("risks", []))
        }

