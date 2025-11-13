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
from agents.tracing import log_trace
from agents.golden_facts import save_golden_facts, load_golden_facts


def create_workflow_graph() -> StateGraph:
    """Create LangGraph workflow with multi-agent system"""
    
    # Define node functions
    async def initialize_node(state: WorkflowState) -> Dict[str, Any]:
        """Initialize MCP session"""
        url = state.get("mcp_server_url", "http://localhost:3333/mcp")
        mcp_caller = McpToolCaller(url, "", state.get("run_id"))
        session_id = await mcp_caller.initialize_session("langgraph-orchestrator")
        print(f"✓ MCP session initialized: {session_id}")
        
        return {
            "mcp_caller": mcp_caller,
            "session_id": session_id
        }
    
    async def ingestion_node(state: WorkflowState) -> Dict[str, Any]:
        """Ingestion agent node"""
        run_id = state.get("run_id")
        log_trace(run_id, {"node": "ingestion", "event": "start"})
        mcp_caller = state["mcp_caller"]
        deal_id = state["deal_id"]
        data_dir = state["data_dir"]
        
        # Get model from state or env var
        model = state.get("llm_model") or os.getenv("LLM_MODEL", "gpt-3.5-turbo")
        agent = IngestionAgent(mcp_caller, use_llm=True, model=model)
        
        # Discover files
        files = await agent.discover_files(data_dir)
        
        # Ingest data
        results = await agent.ingest_all(deal_id, data_dir)
        
        # Validate ingestion
        validation = await agent.validate_ingestion(results)
        
        warnings = validation.get("warnings", [])
        combined_errors = state.get("errors", []) + warnings
        log_trace(run_id, {
            "node": "ingestion",
            "event": "completed",
            "files_ingested": len(results.get("ingested", [])),
            "warnings": warnings,
        })
        return {
            "discovered_files": files,
            "ingestion_results": results,
            "errors": combined_errors
        }
    
    async def kpi_computation_node(state: WorkflowState) -> Dict[str, Any]:
        """KPI computation agent node"""
        run_id = state.get("run_id")
        log_trace(run_id, {"node": "kpi_computation", "event": "start"})
        mcp_caller = state["mcp_caller"]
        deal_id = state["deal_id"]
        
        # Get model from state or env var
        model = state.get("llm_model") or os.getenv("LLM_MODEL", "gpt-3.5-turbo")
        agent = KPIComputationAgent(mcp_caller, use_llm=True, model=model)
        
        # Compute KPIs
        kpi_results = await agent.compute_kpis(deal_id)
        if not isinstance(kpi_results, dict) or "created" not in kpi_results:
            raise ValueError("compute_kpis returned unexpected shape, expected dict with 'created' key")
        created = kpi_results.get("created") or []
        if not isinstance(created, list):
            raise ValueError("compute_kpis 'created' field must be a list")
        print(f"✓ Computed KPIs: {len(created)} KPIs created")
        
        # Validate KPIs
        validation = await agent.validate_kpis(kpi_results)
        
        errors = state.get("errors", [])
        if not validation["passed"]:
            errors.extend(validation.get("warnings", []))
        log_trace(run_id, {
            "node": "kpi_computation",
            "event": "completed",
            "kpis_computed": len(kpi_results.get("created", [])),
            "warnings": validation.get("warnings", []),
        })
        
        return {
            "kpi_results": kpi_results,
            "errors": errors
        }
    
    async def get_snapshot_node(state: WorkflowState) -> Dict[str, Any]:
        """Get Golden Facts snapshot"""
        run_id = state.get("run_id")
        log_trace(run_id, {"node": "get_snapshot", "event": "start"})
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
            
            if not isinstance(snapshot, list):
                raise ValueError("get_golden_facts returned unexpected shape, expected list of KPI entries")
            
            snapshot_size = len(snapshot)
            print(f"✓ Retrieved {snapshot_size} approved KPIs")
            company_name = state.get("company_name")
            period_end = state.get("period_end")
            try:
                path = save_golden_facts(company_name, period_end, {"snapshot": snapshot})
                print(f"✓ Golden facts saved to: {path}")
            except Exception as save_err:
                print(f"⚠ Failed to save golden facts: {save_err}")
            log_trace(run_id, {
                "node": "get_snapshot",
                "event": "completed",
                "snapshot_size": snapshot_size,
            })
            return {"snapshot": snapshot}
        except Exception as e:
            print(f"✗ Failed to get snapshot: {e}")
            log_trace(run_id, {
                "node": "get_snapshot",
                "event": "error",
                "error": str(e),
            })
            return {"snapshot": [], "errors": state.get("errors", []) + [str(e)]}
    
    async def content_generation_node(state: WorkflowState) -> Dict[str, Any]:
        """Content generation agent node"""
        run_id = state.get("run_id")
        log_trace(run_id, {"node": "content_generation", "event": "start"})
        mcp_caller = state["mcp_caller"]
        deal_id = state["deal_id"]
        company_name = state.get("company_name")
        period_end = state.get("period_end")
        
        golden_snapshot = None
        try:
            golden_snapshot = load_golden_facts(company_name, period_end)
        except Exception as load_err:
            print(f"⚠ Failed to load golden facts, falling back to in memory snapshot: {load_err}")
        
        if golden_snapshot is not None:
            snapshot = golden_snapshot.get("snapshot", golden_snapshot)
            print("✓ Using persisted golden facts snapshot for content generation")
        else:
            snapshot = state.get("snapshot") or []
            print("✓ Using in memory snapshot for content generation")
        
        # Get model from state or env var
        model = state.get("llm_model") or os.getenv("LLM_MODEL", "gpt-3.5-turbo")
        agent = ContentGenerationAgent(mcp_caller, use_llm=True, model=model)
        
        # Generate content
        bullets = await agent.generate_content(deal_id, snapshot)
        
        # Validate content
        validation = await agent.validate_content(bullets)
        
        errors = state.get("errors", [])
        if not validation["passed"]:
            errors.extend(validation.get("warnings", []))
        log_trace(run_id, {
            "node": "content_generation",
            "event": "completed",
            "bullets_generated": len(bullets.get("thesis", [])) + len(bullets.get("risks", [])),
            "warnings": validation.get("warnings", []),
        })
        
        return {
            "bullets": bullets,
            "errors": errors
        }
    
    async def render_node(state: WorkflowState) -> Dict[str, Any]:
        """Render one-pager markdown"""
        run_id = state.get("run_id")
        log_trace(run_id, {"node": "render", "event": "start"})
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
            if not isinstance(markdown, str) or len(markdown.strip()) < 100:
                raise ValueError("render_onepager_markdown returned too little content or wrong type")
            
            print(f"✓ Generated one-pager markdown ({len(markdown)} chars)")
            log_trace(run_id, {
                "node": "render",
                "event": "completed",
                "markdown_chars": len(markdown),
            })
            return {"markdown": markdown}
        except Exception as e:
            print(f"✗ Failed to render one-pager: {e}")
            log_trace(run_id, {
                "node": "render",
                "event": "error",
                "error": str(e),
            })
            return {"markdown": "", "errors": state.get("errors", []) + [str(e)]}
    
    async def save_output_node(state: WorkflowState) -> Dict[str, Any]:
        """Save output file"""
        run_id = state.get("run_id")
        log_trace(run_id, {"node": "save_output", "event": "start"})
        markdown = state["markdown"]
        company_name = state["company_name"]
        period_end = state["period_end"]
        
        if not markdown:
            log_trace(run_id, {
                "node": "save_output",
                "event": "completed",
                "status": "skipped",
                "reason": "no_markdown"
            })
            return {"errors": state.get("errors", []) + ["No markdown to save"]}
        
        safe_name = company_name.replace(" ", "_").replace(",", "").replace(".", "")
        output_dir = "output"
        output_file = f"{output_dir}/LP_OnePager_{safe_name}_{period_end.replace('-', '_')}.md"
        
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w') as f:
            f.write(markdown)
        
        print(f"✓ Saved one-pager to: {output_file}")
        log_trace(run_id, {
            "node": "save_output",
            "event": "completed",
            "output_file": output_file,
        })
        return {"output_file": output_file}
    
    async def register_output_node(state: WorkflowState) -> Dict[str, Any]:
        """Register output artifact"""
        run_id = state.get("run_id")
        log_trace(run_id, {"node": "register_output", "event": "start"})
        mcp_caller = state["mcp_caller"]
        deal_id = state["deal_id"]
        output_file = state.get("output_file")
        
        if not output_file:
            log_trace(run_id, {
                "node": "register_output",
                "event": "completed",
                "status": "skipped",
                "reason": "no_output_file"
            })
            return {}
        
        try:
            result = await mcp_caller.call_tool("register_output", {
                "deal_id": deal_id,
                "recipe": "LP_OnePager_v1",
                "kind": "markdown",
                "uri": f"file://{os.path.abspath(output_file)}"
            })
            new_run_id = None
            if isinstance(result, dict):
                new_run_id = result.get("run_id")
            if new_run_id:
                new_run_id = str(new_run_id)
                print(f"✓ Output registered (run_id={new_run_id})")
                mcp_caller.run_id = new_run_id
                log_trace(new_run_id, {
                    "node": "register_output",
                    "event": "completed",
                    "run_id": new_run_id,
                })
                return {"run_id": new_run_id}
            print("✓ Output registered")
            log_trace(run_id, {
                "node": "register_output",
                "event": "completed",
                "status": "no_run_id",
            })
        except Exception as e:
            print(f"⚠ Failed to register output: {e}")
            log_trace(run_id, {
                "node": "register_output",
                "event": "error",
                "error": str(e),
            })
        
        return {}
    
    async def finalize_node(state: WorkflowState) -> Dict[str, Any]:
        """Finalize workflow and create summary"""
        run_id = state.get("run_id")
        log_trace(run_id, {"node": "finalize", "event": "start"})
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
            "session_id": state.get("session_id"),
            "session_label": state.get("session_label"),
            "run_id": state.get("run_id"),
            "errors": state.get("errors", [])
        }
        
        log_trace(run_id, {
            "node": "finalize",
            "event": "completed",
            "success": summary["success"],
            "files_ingested": summary["files_ingested"],
            "kpis_computed": summary["kpis_computed"],
            "output_file": summary["output_file"],
        })
        
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
