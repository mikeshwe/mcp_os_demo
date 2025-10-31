"""
LangGraph Workflow for LP One-Pager Generation
Uses multi-agent system with explicit state management
"""

import os
from typing import Dict, Any
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from agents.graph_state import WorkflowState
from agents.mcp_tools import McpToolCaller
from agents.ingestion_agent import IngestionAgent
from agents.kpi_agent import KPIComputationAgent
from agents.content_agent import ContentGenerationAgent


def create_workflow_graph() -> StateGraph:
    """Create LangGraph workflow with multi-agent system"""
    
    # Define node functions
    async def initialize_node(state: WorkflowState) -> Dict[str, Any]:
        """Initialize MCP session"""
        url = state.get("mcp_server_url", "http://localhost:3333/mcp")
        mcp_caller = McpToolCaller(url, "")
        session_id = await mcp_caller.initialize_session("langgraph-orchestrator")
        print(f"✓ MCP session initialized: {session_id}")
        
        return {
            "mcp_caller": mcp_caller,
            "session_id": session_id
        }
    
    async def ingestion_node(state: WorkflowState) -> Dict[str, Any]:
        """Ingestion agent node"""
        mcp_caller = state["mcp_caller"]
        deal_id = state["deal_id"]
        data_dir = state["data_dir"]
        
        agent = IngestionAgent(mcp_caller, use_llm=True)
        
        # Discover files
        files = await agent.discover_files(data_dir)
        
        # Ingest data
        results = await agent.ingest_all(deal_id, data_dir)
        
        # Validate ingestion
        validation = await agent.validate_ingestion(results)
        
        if not validation["passed"]:
            errors = state.get("errors", [])
            errors.extend(validation.get("warnings", []))
        
        return {
            "discovered_files": files,
            "ingestion_results": results,
            "errors": state.get("errors", []) + validation.get("warnings", [])
        }
    
    async def kpi_computation_node(state: WorkflowState) -> Dict[str, Any]:
        """KPI computation agent node"""
        mcp_caller = state["mcp_caller"]
        deal_id = state["deal_id"]
        
        agent = KPIComputationAgent(mcp_caller, use_llm=True)
        
        # Compute KPIs
        kpi_results = await agent.compute_kpis(deal_id)
        
        # Validate KPIs
        validation = await agent.validate_kpis(kpi_results)
        
        errors = state.get("errors", [])
        if not validation["passed"]:
            errors.extend(validation.get("warnings", []))
        
        return {
            "kpi_results": kpi_results,
            "errors": errors
        }
    
    async def get_snapshot_node(state: WorkflowState) -> Dict[str, Any]:
        """Get Golden Facts snapshot"""
        mcp_caller = state["mcp_caller"]
        deal_id = state["deal_id"]
        
        try:
            result = await mcp_caller.call_tool("get_golden_facts", {"deal_id": deal_id})
            
            # Handle MCP response format
            snapshot = []
            if isinstance(result, dict):
                if "snapshot" in result:
                    snapshot = result["snapshot"]
                elif "content" in result:
                    content = result.get("content", [])
                    if content and len(content) > 0:
                        text = content[0].get("text", "")
                        if text:
                            import json
                            snapshot_data = json.loads(text)
                            snapshot = snapshot_data.get("snapshot", [])
            
            # Ensure snapshot items have correct format
            for item in snapshot:
                if isinstance(item, dict) and "value" in item:
                    if isinstance(item["value"], str):
                        try:
                            item["value"] = float(item["value"])
                        except (ValueError, TypeError):
                            pass
            
            print(f"✓ Retrieved {len(snapshot)} approved KPIs")
            return {"snapshot": snapshot}
        except Exception as e:
            print(f"✗ Failed to get snapshot: {e}")
            return {"snapshot": [], "errors": state.get("errors", []) + [str(e)]}
    
    async def content_generation_node(state: WorkflowState) -> Dict[str, Any]:
        """Content generation agent node"""
        mcp_caller = state["mcp_caller"]
        deal_id = state["deal_id"]
        snapshot = state["snapshot"]
        
        agent = ContentGenerationAgent(mcp_caller, use_llm=True)
        
        # Generate content
        bullets = await agent.generate_content(deal_id, snapshot)
        
        # Validate content
        validation = await agent.validate_content(bullets)
        
        errors = state.get("errors", [])
        if not validation["passed"]:
            errors.extend(validation.get("warnings", []))
        
        return {
            "bullets": bullets,
            "errors": errors
        }
    
    async def render_node(state: WorkflowState) -> Dict[str, Any]:
        """Render one-pager markdown"""
        mcp_caller = state["mcp_caller"]
        deal_id = state["deal_id"]
        company_name = state["company_name"]
        period_end = state["period_end"]
        snapshot = state["snapshot"]
        bullets = state["bullets"]
        
        try:
            result = await mcp_caller.call_tool("render_onepager_markdown", {
                "company": company_name,
                "period_end": period_end,
                "snapshot": snapshot,
                "bullets": bullets,
                "deal_id": deal_id
            })
            
            # Handle MCP response format
            markdown = ""
            if isinstance(result, dict):
                if "markdown" in result:
                    markdown = result["markdown"]
                elif "content" in result:
                    content = result.get("content", [])
                    if content and len(content) > 0:
                        text = content[0].get("text", "")
                        if text:
                            import json
                            result_data = json.loads(text)
                            markdown = result_data.get("markdown", "")
            
            # Unescape markdown
            markdown = markdown.replace('\\n', '\n').replace('\\u2014', '—').replace('\\"', '"')
            
            print(f"✓ Generated one-pager markdown ({len(markdown)} chars)")
            return {"markdown": markdown}
        except Exception as e:
            print(f"✗ Failed to render one-pager: {e}")
            return {"markdown": "", "errors": state.get("errors", []) + [str(e)]}
    
    async def save_output_node(state: WorkflowState) -> Dict[str, Any]:
        """Save output file"""
        markdown = state["markdown"]
        data_dir = state["data_dir"]
        company_name = state["company_name"]
        period_end = state["period_end"]
        
        if not markdown:
            return {"errors": state.get("errors", []) + ["No markdown to save"]}
        
        safe_name = company_name.replace(" ", "_").replace(",", "").replace(".", "")
        output_file = f"{data_dir}/LP_OnePager_{safe_name}_{period_end.replace('-', '_')}.md"
        
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w') as f:
            f.write(markdown)
        
        print(f"✓ Saved one-pager to: {output_file}")
        return {"output_file": output_file}
    
    async def register_output_node(state: WorkflowState) -> Dict[str, Any]:
        """Register output artifact"""
        mcp_caller = state["mcp_caller"]
        deal_id = state["deal_id"]
        output_file = state.get("output_file")
        
        if not output_file:
            return {}
        
        try:
            await mcp_caller.call_tool("register_output", {
                "deal_id": deal_id,
                "recipe": "LP_OnePager_v1",
                "kind": "markdown",
                "uri": f"file://{os.path.abspath(output_file)}"
            })
            print("✓ Output registered")
        except Exception as e:
            print(f"⚠ Failed to register output: {e}")
        
        return {}
    
    async def finalize_node(state: WorkflowState) -> Dict[str, Any]:
        """Finalize workflow and create summary"""
        ingestion_results = state.get("ingestion_results", {})
        kpi_results = state.get("kpi_results", {})
        snapshot = state.get("snapshot", [])
        bullets = state.get("bullets", {})
        
        summary = {
            "success": len(state.get("errors", [])) == 0,
            "files_ingested": len(ingestion_results.get("ingested", [])),
            "kpis_computed": len(kpi_results.get("created", [])),
            "snapshot_size": len(snapshot),
            "bullets_generated": len(bullets.get("thesis", [])) + len(bullets.get("risks", [])),
            "output_file": state.get("output_file"),
            "errors": state.get("errors", [])
        }
        
        return {
            "success": summary["success"],
            "summary": summary
        }
    
    # Create workflow graph
    workflow = StateGraph(WorkflowState)
    
    # Add nodes
    workflow.add_node("initialize", initialize_node)
    workflow.add_node("ingestion", ingestion_node)
    workflow.add_node("kpi_computation", kpi_computation_node)
    workflow.add_node("get_snapshot", get_snapshot_node)
    workflow.add_node("content_generation", content_generation_node)
    workflow.add_node("render", render_node)
    workflow.add_node("save_output", save_output_node)
    workflow.add_node("register_output", register_output_node)
    workflow.add_node("finalize", finalize_node)
    
    # Define edges
    workflow.set_entry_point("initialize")
    workflow.add_edge("initialize", "ingestion")
    workflow.add_edge("ingestion", "kpi_computation")
    workflow.add_edge("kpi_computation", "get_snapshot")
    workflow.add_edge("get_snapshot", "content_generation")
    workflow.add_edge("content_generation", "render")
    workflow.add_edge("render", "save_output")
    workflow.add_edge("save_output", "register_output")
    workflow.add_edge("register_output", "finalize")
    workflow.add_edge("finalize", END)
    
    return workflow


def create_workflow_app(mcp_server_url: str = "http://localhost:3333/mcp"):
    """Create compiled workflow app"""
    workflow = create_workflow_graph()
    return workflow.compile()

