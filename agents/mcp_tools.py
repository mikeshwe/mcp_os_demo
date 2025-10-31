"""
MCP Tool Wrapper for LangChain
Provides LangChain-compatible tools that call MCP server via HTTP
"""

import httpx
import json
from typing import Any, Optional
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field


class McpToolCaller:
    """Handles MCP protocol communication over HTTP"""
    
    def __init__(self, server_url: str, session_id: str):
        self.server_url = server_url
        self.session_id = session_id
        self.request_id = 1
    
    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Call an MCP tool and return the result"""
        self.request_id += 1
        
        payload = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                self.server_url,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                    "MCP-Session-Id": self.session_id
                },
                json=payload
            )
            response.raise_for_status()
            result = response.json()
            
            # Extract content from MCP response
            if "result" in result:
                result_obj = result["result"]
                # Check if result has content array (MCP format)
                if "content" in result_obj:
                    content = result_obj.get("content", [])
                    if content and len(content) > 0:
                        text = content[0].get("text", "")
                        if text:
                            try:
                                return json.loads(text)
                            except:
                                return {"raw": text}
                # Otherwise return the result object directly
                return result_obj
            return result
    
    async def initialize_session(self, client_name: str = "langchain-agent") -> str:
        """Initialize MCP session and return session ID"""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": client_name, "version": "1.0"}
            }
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                self.server_url,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream"
                },
                json=payload
            )
            response.raise_for_status()
            
            # Extract session ID from headers
            session_id = response.headers.get("mcp-session-id") or response.headers.get("MCP-Session-Id")
            if session_id:
                self.session_id = session_id
                return session_id
            else:
                raise ValueError("No session ID returned from MCP server")


class McpTool(BaseTool):
    """LangChain tool wrapper for MCP tools"""
    
    name: str = Field(description="Name of the MCP tool")
    description: str = Field(description="Description of what the tool does")
    mcp_caller: McpToolCaller = Field(description="MCP tool caller instance")
    
    def _run(self, **kwargs: Any) -> str:
        """Synchronous run (not recommended for async)"""
        import asyncio
        return asyncio.run(self._arun(**kwargs))
    
    async def _arun(self, **kwargs: Any) -> str:
        """Asynchronous run"""
        result = await self.mcp_caller.call_tool(self.name, kwargs)
        return json.dumps(result, indent=2)
    
    def __init__(self, name: str, description: str, mcp_caller: McpToolCaller, **kwargs):
        super().__init__(
            name=name,
            description=description,
            mcp_caller=mcp_caller,
            **kwargs
        )


def create_mcp_tools(mcp_caller: McpToolCaller) -> list[McpTool]:
    """Create LangChain tools for all available MCP tools"""
    
    # Define tool descriptions based on PRD
    tool_descriptions = {
        "ingest_excel": "Ingest Excel file (.xlsx) and extract table cells. Detects periods, units, currency. Supports multi-sheet import.",
        "ingest_csv": "Ingest CSV file and extract table cells. Generic ERP/BI data loader.",
        "ingest_memo": "Ingest memo document (.txt/.md) and split into chunks with vector embeddings for semantic search.",
        "ingest_billing": "Ingest billing CSV (MRR movements). Stub for future Stripe/Zuora integration.",
        "ingest_edgar_xbrl": "Ingest SEC EDGAR XBRL CSV export and map XBRL concepts to canonical labels.",
        "ingest_snowflake": "Ingest Snowflake CSV export. Proxy for future direct connector.",
        "compute_kpis": "Compute core KPIs (Revenue_LTM, YoY_Growth, Gross_Margin, EBITDA_Margin) from ingested data.",
        "get_golden_facts": "Fetch approved GoldenFacts (KPI snapshot) for a deal.",
        "get_kpi_lineage": "Get lineage (underlying cells) for KPI values in a deal for traceability.",
        "render_onepager_markdown": "Render a Markdown LP one-pager from snapshot + optional bullets with lineage links.",
        "register_output": "Create a Runs/Outputs row to track an artifact and its lineage.",
    }
    
    tools = []
    for tool_name, description in tool_descriptions.items():
        tool = McpTool(
            name=tool_name,
            description=description,
            mcp_caller=mcp_caller
        )
        tools.append(tool)
    
    return tools

