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
    
    def __init__(self, mcp_caller: McpToolCaller, use_llm: bool = True, model: str = None):
        self.mcp_caller = mcp_caller
        self.use_llm = use_llm
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
        # Check if data exists by trying to get golden facts
        try:
            result = await self.mcp_caller.call_tool("get_golden_facts", {"deal_id": deal_id})
            
            # Simple validation - check if we have any data
            has_data = False
            if isinstance(result, dict):
                if "snapshot" in result:
                    has_data = len(result["snapshot"]) > 0
                elif "content" in result:
                    content = result.get("content", [])
                    if content and len(content) > 0:
                        text = content[0].get("text", "")
                        if text:
                            import json
                            snapshot_data = json.loads(text)
                            has_data = len(snapshot_data.get("snapshot", [])) > 0
            
            return {
                "has_data": has_data,
                "data_quality": "good" if has_data else "poor",
                "recommendations": [] if has_data else ["Ensure data is ingested before computing KPIs"]
            }
        except Exception as e:
            return {
                "has_data": False,
                "data_quality": "unknown",
                "recommendations": [f"Data validation failed: {e}"]
            }
    
    async def determine_parameters(self, quality: Dict[str, Any], deal_id: str) -> Dict[str, Any]:
        """Determine optimal KPI computation parameters"""
        if not self.use_llm or not self.llm:
            # Default parameters
            return {
                "periods_to_sum": 4,
                "approve": True,
                "ttl_days": 90
            }
        
        # Use LLM to determine parameters based on data quality
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a financial analyst. Determine optimal KPI computation parameters based on data quality."""),
            ("human", """Data Quality: {quality}
            
            Determine parameters:
            - periods_to_sum: How many periods to sum for LTM (typically 4 for quarterly)
            - approve: Whether to auto-approve KPIs (true/false)
            - ttl_days: Time-to-live for KPI values (typically 90)
            
            Return JSON:
            {{"periods_to_sum": 4, "approve": true, "ttl_days": 90}}""")
        ])
        
        parser = JsonOutputParser()
        chain = prompt | self.llm | parser
        
        try:
            result = await chain.ainvoke({"quality": str(quality)})
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

