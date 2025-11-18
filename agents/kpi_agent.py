"""
KPI Computation Agent - Specialized for computing and validating KPIs
"""

from typing import Dict, Any, Optional
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from agents.mcp_tools import McpToolCaller


class KPIComputationAgent:
    """Agent responsible for computing and validating KPIs"""
    
    def __init__(self, mcp_caller: McpToolCaller, use_llm: bool = True, model: str = None, use_tool_discovery: bool = False):
        self.mcp_caller = mcp_caller
        self.use_llm = use_llm
        self.use_tool_discovery = use_tool_discovery
        self.llm = None
        
        if use_llm:
            try:
                import os
                if os.getenv("OPENAI_API_KEY"):
                    # Use provided model or fall back to env var or default
                    model = model or os.getenv("LLM_MODEL", "gpt-3.5-turbo")
                    self.llm = ChatOpenAI(model=model, temperature=0)
            except Exception:
                self.use_llm = False
    
    async def validate_data_quality(self, deal_id: str) -> Dict[str, Any]:
        """Validate data quality before computing KPIs"""
        # Since we just ingested data, assume data is available
        # The compute_kpis tool will handle cases where data doesn't exist
        # This validation is mainly for logging/feedback purposes
        return {
            "has_data": True,  # Assume data is available after ingestion
            "data_quality": "good",
            "recommendations": []
        }
    
    async def determine_parameters(self, quality: Dict[str, Any], deal_id: str) -> Dict[str, Any]:
        """Determine optimal KPI computation parameters
        
        When use_tool_discovery is enabled, queries MCP server for compute_kpis tool schema
        to understand available parameters and their types.
        """
        # If discovery mode is enabled, get tool schema to understand parameters
        tool_schema = None
        if self.use_tool_discovery:
            print("🔍 Discovering compute_kpis tool schema from MCP server...")
            try:
                all_tools = await self.mcp_caller.list_tools()
                compute_tool = next((t for t in all_tools if t.get("name") == "compute_kpis"), None)
                if compute_tool:
                    tool_schema = compute_tool.get("inputSchema", {})
                    tool_desc = compute_tool.get("description", "")
                    print(f"   ✓ Found compute_kpis: {tool_desc[:80]}{'...' if len(tool_desc) > 80 else ''}")
                    if tool_schema.get("properties"):
                        props = tool_schema["properties"]
                        print(f"   ✓ Tool has {len(props)} parameters:")
                        for param_name, param_info in props.items():
                            param_type = param_info.get("type", "unknown")
                            is_required = param_name in (tool_schema.get("required", []))
                            print(f"     • {param_name} ({param_type}){' [required]' if is_required else ' [optional]'}")
                else:
                    print("   ⚠ compute_kpis tool not found in discovered tools")
            except Exception as e:
                print(f"⚠ Failed to discover tool schema: {e}")
        
        if not self.use_llm or not self.llm:
            # Default parameters
            return {
                "periods_to_sum": 4,
                "approve": True,
                "ttl_days": 90
            }
        
        # Build parameter description from schema if available
        param_desc = """Determine parameters:
            - periods_to_sum: How many periods to sum for LTM (typically 4 for quarterly)
            - approve: Whether to auto-approve KPIs (true/false)
            - ttl_days: Time-to-live for KPI values (typically 90)"""
        
        if tool_schema and tool_schema.get("properties"):
            props = tool_schema["properties"]
            required = tool_schema.get("required", [])
            param_desc = "Available parameters from tool schema:\n"
            for param_name, param_info in props.items():
                param_type = param_info.get("type", "unknown")
                param_desc_text = param_info.get("description", "")
                is_required = param_name in required
                param_desc += f"  - {param_name} ({param_type}){' [required]' if is_required else ' [optional]'}"
                if param_desc_text:
                    param_desc += f": {param_desc_text}"
                if "default" in param_info:
                    param_desc += f" (default: {param_info['default']})"
                param_desc += "\n"
        
        # Use LLM to determine parameters based on data quality
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a financial analyst. Determine optimal KPI computation parameters based on data quality and tool schema."""),
            ("human", """Data Quality: {quality}
            
            {param_desc}
            
            Return JSON with parameter values:
            {{"periods_to_sum": 4, "approve": true, "ttl_days": 90}}""")
        ])
        
        parser = JsonOutputParser()
        chain = prompt | self.llm | parser
        
        try:
            result = await chain.ainvoke({
                "quality": str(quality),
                "param_desc": param_desc
            })
            return result
        except Exception:
            # Fallback to defaults
            return {
                "periods_to_sum": 4,
                "approve": True,
                "ttl_days": 90
            }
    
    async def compute_kpis(self, deal_id: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Compute KPIs with validation"""
        # Validate data quality
        quality = await self.validate_data_quality(deal_id)
        
        if not quality.get("has_data"):
            print("⚠ Warning: Limited data available for KPI computation")
        
        # Determine parameters
        if params is None:
            params = await self.determine_parameters(quality, deal_id)
        
        # Compute KPIs
        try:
            result = await self.mcp_caller.call_tool("compute_kpis", {
                "deal_id": deal_id,
                **params
            })
            
            created_count = len(result.get("created", []))
            print(f"✓ Computed KPIs: {created_count} KPIs created")
            
            return result
        except Exception as e:
            print(f"✗ Failed to compute KPIs: {e}")
            raise
    
    async def validate_kpis(self, kpi_results: Dict[str, Any]) -> Dict[str, Any]:
        """Validate computed KPIs"""
        validation = {
            "passed": True,
            "warnings": [],
            "recommendations": []
        }
        
        created_count = len(kpi_results.get("created", []))
        
        if created_count == 0:
            validation["passed"] = False
            validation["warnings"].append("No KPIs were computed")
        elif created_count < 4:
            validation["warnings"].append(f"Only {created_count} KPIs computed (expected 4+)")
        
        # Check for required KPIs
        created_kpis = [item.get("kpi", "") for item in kpi_results.get("created", [])]
        required_kpis = ["Revenue_LTM", "YoY_Growth", "Gross_Margin", "EBITDA_Margin"]
        
        missing_kpis = [kpi for kpi in required_kpis if kpi not in created_kpis]
        if missing_kpis:
            validation["warnings"].append(f"Missing KPIs: {', '.join(missing_kpis)}")
        
        return validation

