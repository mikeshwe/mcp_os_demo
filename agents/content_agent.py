"""
Content Generation Agent - Specialized for generating narrative content
"""

from typing import Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from agents.mcp_tools import McpToolCaller


class ContentGenerationAgent:
    """Agent responsible for generating narrative content (thesis, risks)"""
    
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
    
    async def analyze_trends(self, snapshot: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze financial trends from snapshot"""
        trends = {
            "revenue_growth": None,
            "margin_trends": [],
            "key_metrics": {}
        }
        
        for item in snapshot:
            kpi = item.get("kpi", "")
            value = item.get("value", 0)
            
            if "Revenue" in kpi or "revenue" in kpi.lower():
                trends["key_metrics"]["revenue"] = value
            if "Growth" in kpi or "growth" in kpi.lower():
                trends["revenue_growth"] = value
            if "Margin" in kpi or "margin" in kpi.lower():
                trends["margin_trends"].append({"kpi": kpi, "value": value})
        
        return trends
    
    async def search_memo(self, deal_id: str, trends: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Search memo chunks for relevant insights (using vector search via render tool)"""
        # Note: This would ideally use a dedicated search tool
        # For now, we'll rely on the render tool's built-in vector search
        # when generating the final output
        return []
    
    async def generate_content(self, deal_id: str, snapshot: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """Generate investment thesis and risks"""
        
        # Analyze trends
        trends = await self.analyze_trends(snapshot)
        
        # Format snapshot for LLM
        snapshot_text = "\n".join([
            f"- {item['kpi']}: {item['value']} {item.get('unit', '')}"
            for item in snapshot[:10]  # Limit to first 10 KPIs
        ])
        
        if not self.use_llm or not self.llm:
            # Fallback content
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
        
        # Generate thesis bullets
        thesis_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a financial analyst generating investment thesis bullets for LP one-pagers.
            Focus on strengths, opportunities, and competitive advantages. Be specific and data-driven."""),
            ("human", """Financial Snapshot:
{snapshot}

Trends:
{trends}

Generate 3-5 investment thesis bullets highlighting strengths and opportunities.
Return JSON array: ["bullet 1", "bullet 2", ...]""")
        ])
        
        thesis_parser = JsonOutputParser()
        thesis_chain = thesis_prompt | self.llm | thesis_parser
        
        # Generate risks bullets
        risks_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a financial analyst identifying key risks with mitigants for LP one-pagers.
            Focus on realistic risks and how they are being addressed. Be specific and balanced."""),
            ("human", """Financial Snapshot:
{snapshot}

Trends:
{trends}

Generate 3-5 key risks with mitigants.
Return JSON array: ["risk 1 (mitigant: ...)", "risk 2 (mitigant: ...)", ...]""")
        ])
        
        risks_parser = JsonOutputParser()
        risks_chain = risks_prompt | self.llm | risks_parser
        
        try:
            thesis_result = await thesis_chain.ainvoke({
                "snapshot": snapshot_text,
                "trends": str(trends)
            })
            risks_result = await risks_chain.ainvoke({
                "snapshot": snapshot_text,
                "trends": str(trends)
            })
            
            # Ensure results are lists
            thesis = thesis_result if isinstance(thesis_result, list) else thesis_result.get("thesis", [])
            risks = risks_result if isinstance(risks_result, list) else risks_result.get("risks", [])
            
            print(f"✓ Generated {len(thesis)} thesis bullets and {len(risks)} risks")
            
            return {
                "thesis": thesis[:5],  # Limit to 5
                "risks": risks[:5]     # Limit to 5
            }
        except Exception as e:
            print(f"✗ Failed to generate content with LLM: {e}")
            # Fallback to default content
            return {
                "thesis": ["Strong revenue growth trajectory", "Market leadership position", "Operational efficiency improvements"],
                "risks": ["Customer concentration", "Competitive pressure", "Macroeconomic uncertainty"]
            }
    
    async def validate_content(self, bullets: Dict[str, List[str]]) -> Dict[str, Any]:
        """Validate generated content quality"""
        validation = {
            "passed": True,
            "warnings": [],
            "recommendations": []
        }
        
        thesis_count = len(bullets.get("thesis", []))
        risks_count = len(bullets.get("risks", []))
        
        if thesis_count < 3:
            validation["warnings"].append(f"Only {thesis_count} thesis bullets generated (recommended: 3-5)")
        
        if risks_count < 3:
            validation["warnings"].append(f"Only {risks_count} risk bullets generated (recommended: 3-5)")
        
        if thesis_count == 0:
            validation["passed"] = False
        
        if risks_count == 0:
            validation["passed"] = False
        
        return validation

