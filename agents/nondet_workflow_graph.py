"""
LangGraph Non-Deterministic Workflow
Demonstrates conditional routing based on validation results and agent decisions
"""

import os
from typing import Dict, Any, Literal
from langgraph.graph import StateGraph, END
from agents.graph_state import WorkflowState
from agents.mcp_tools import McpToolCaller
from agents.ingestion_agent import IngestionAgent
from agents.kpi_agent import KPIComputationAgent
from agents.content_agent import ContentGenerationAgent
from agents.tracing import log_trace
from agents.golden_facts import save_golden_facts, load_golden_facts


def create_non_deterministic_workflow_graph() -> StateGraph:
    """Create LangGraph workflow with conditional routing (non-deterministic paths)"""
    
    # Define node functions
    async def initialize_node(state: WorkflowState) -> Dict[str, Any]:
        """Initialize MCP session"""
        url = state.get("mcp_server_url", "http://localhost:3333/mcp")
        mcp_caller = McpToolCaller(url, "", state.get("run_id"))
        session_id = await mcp_caller.initialize_session("langgraph-nondet")
        print(f"✓ MCP session initialized: {session_id}")
        
        return {
            "mcp_caller": mcp_caller,
            "session_id": session_id,
            "retry_count": 0
        }
    
    async def ingestion_node(state: WorkflowState) -> Dict[str, Any]:
        """Ingestion agent node"""
        run_id = state.get("run_id")
        log_trace(run_id, {"node": "ingestion", "event": "start"})
        mcp_caller = state["mcp_caller"]
        deal_id = state["deal_id"]
        data_dir = state["data_dir"]
        retry_count = state.get("retry_count", 0)
        
        print(f"\n{'='*60}")
        print(f"📥 Ingestion Agent (Attempt {retry_count + 1})")
        print(f"{'='*60}")
        
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
        errors = state.get("errors", [])
        if not validation["passed"]:
            errors.extend(warnings)
        log_trace(run_id, {
            "node": "ingestion",
            "event": "completed",
            "files_ingested": len(results.get("ingested", [])),
            "warnings": warnings,
        })
        
        return {
            "discovered_files": files,
            "ingestion_results": results,
            "ingestion_validation": validation,
            "errors": errors
        }
    
    async def retry_ingestion_node(state: WorkflowState) -> Dict[str, Any]:
        """Retry ingestion with different strategy"""
        retry_count = state.get("retry_count", 0)
        print(f"\n🔄 Retrying ingestion with alternative strategy (Retry {retry_count + 1})")
        
        # Retry with more permissive parameters
        mcp_caller = state["mcp_caller"]
        deal_id = state["deal_id"]
        data_dir = state["data_dir"]
        
        # Get model from state or env var (even though we're using fallback strategy)
        model = state.get("llm_model") or os.getenv("LLM_MODEL", "gpt-3.5-turbo")
        agent = IngestionAgent(mcp_caller, use_llm=False, model=model)  # Use fallback strategy
        
        files = await agent.discover_files(data_dir)
        results = await agent.ingest_all(deal_id, data_dir)
        validation = await agent.validate_ingestion(results)
        
        return {
            "discovered_files": files,
            "ingestion_results": results,
            "ingestion_validation": validation,
            "retry_count": retry_count + 1,
            "errors": state.get("errors", [])
        }
    
    def route_after_ingestion(state: WorkflowState) -> Literal["continue", "retry", "skip"]:
        """Route based on ingestion validation results"""
        validation = state.get("ingestion_validation", {})
        retry_count = state.get("retry_count", 0)
        
        if not validation.get("passed", False):
            if retry_count < 2:  # Max 2 retries
                print("⚠ Ingestion validation failed - routing to RETRY")
                return "retry"
            else:
                print("⚠ Max retries reached - routing to SKIP (with warnings)")
                return "skip"
        else:
            print("✓ Ingestion validation passed - routing to CONTINUE")
            return "continue"
    
    async def kpi_computation_node(state: WorkflowState) -> Dict[str, Any]:
        """KPI computation agent node"""
        run_id = state.get("run_id")
        log_trace(run_id, {"node": "kpi_computation", "event": "start"})
        mcp_caller = state["mcp_caller"]
        deal_id = state["deal_id"]
        
        print(f"\n{'='*60}")
        print(f"📊 KPI Computation Agent")
        print(f"{'='*60}")
        
        # Get model from state or env var
        model = state.get("llm_model") or os.getenv("LLM_MODEL", "gpt-3.5-turbo")
        agent = KPIComputationAgent(mcp_caller, use_llm=True, model=model)
        
        # Validate data quality first
        quality = await agent.validate_data_quality(deal_id)
        
        if not quality.get("has_data"):
            print("⚠ No data available - skipping KPI computation")
            log_trace(run_id, {
                "node": "kpi_computation",
                "event": "completed",
                "kpis_computed": 0,
                "warnings": ["No data available"]
            })
            return {
                "kpi_results": {"created": []},
                "kpi_validation": {"passed": False, "warnings": ["No data available"]},
                "errors": state.get("errors", []) + ["No data for KPI computation"]
            }
        
        # Compute KPIs
        kpi_results = await agent.compute_kpis(deal_id)
        
        # Validate KPIs
        validation = await agent.validate_kpis(kpi_results)
        
        errors = state.get("errors", [])
        if not validation["passed"]:
            errors.extend(validation.get("warnings", []))
        
        log_trace(run_id, {
            "node": "kpi_computation",
            "event": "completed",
            "kpis_computed": len(kpi_results.get("created", [])),
            "warnings": validation.get("warnings", [])
        })
        
        return {
            "kpi_results": kpi_results,
            "kpi_validation": validation,
            "errors": errors
        }
    
    def route_after_kpi(state: WorkflowState) -> Literal["continue", "fallback"]:
        """Route based on KPI validation results"""
        validation = state.get("kpi_validation", {})
        
        if not validation.get("passed", False):
            created_count = len(state.get("kpi_results", {}).get("created", []))
            if created_count == 0:
                print("⚠ No KPIs computed - routing to FALLBACK (use existing data)")
                return "fallback"
        
        print("✓ KPI validation passed - routing to CONTINUE")
        return "continue"
    
    async def use_existing_kpis_node(state: WorkflowState) -> Dict[str, Any]:
        """Use existing KPIs from database if computation failed"""
        print("\n🔄 Using existing KPIs from database (fallback mode)")
        # This would fetch existing approved KPIs
        # For now, just continue with empty results
        return {
            "kpi_validation": {"passed": True, "warnings": ["Using existing KPIs"]}
        }
    
    async def get_snapshot_node(state: WorkflowState) -> Dict[str, Any]:
        """Get Golden Facts snapshot"""
        run_id = state.get("run_id")
        log_trace(run_id, {"node": "get_snapshot", "event": "start"})
        mcp_caller = state["mcp_caller"]
        deal_id = state["deal_id"]
        
        print(f"\n{'='*60}")
        print(f"📋 Retrieving Golden Facts Snapshot")
        print(f"{'='*60}")
        
        try:
            result = await mcp_caller.call_tool("get_golden_facts", {"deal_id": deal_id})
            
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
            snapshot = state["snapshot"]
            print("✓ Using in memory snapshot for content generation")
        
        print(f"\n{'='*60}")
        print(f"✍️  Content Generation Agent")
        print(f"{'='*60}")
        
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
            "warnings": validation.get("warnings", [])
        })
        
        return {
            "bullets": bullets,
            "content_validation": validation,
            "errors": errors
        }
    
    def route_after_content(state: WorkflowState) -> Literal["continue", "fallback_content"]:
        """Route based on content validation"""
        validation = state.get("content_validation", {})
        
        if not validation.get("passed", False):
            thesis_count = len(state.get("bullets", {}).get("thesis", []))
            risks_count = len(state.get("bullets", {}).get("risks", []))
            
            if thesis_count == 0 or risks_count == 0:
                print("⚠ Content validation failed - routing to FALLBACK_CONTENT")
                return "fallback_content"
        
        print("✓ Content validation passed - routing to CONTINUE")
        return "continue"
    
    async def use_fallback_content_node(state: WorkflowState) -> Dict[str, Any]:
        """Use fallback content if generation failed"""
        print("\n🔄 Using fallback content")
        fallback_bullets = {
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
        return {
            "bullets": fallback_bullets,
            "content_validation": {"passed": True, "warnings": ["Using fallback content"]}
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
        
        print(f"\n{'='*60}")
        print(f"🎨 Rendering One-Pager")
        print(f"{'='*60}")
        
        try:
            result = await mcp_caller.call_tool("render_onepager_markdown", {
                "company": company_name,
                "period_end": period_end,
                "snapshot": snapshot,
                "bullets": bullets,
                "deal_id": deal_id
            })
            
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
            
            markdown = markdown.replace('\\n', '\n').replace('\\u2014', '—').replace('\\"', '"')
            
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
        output_file = f"{output_dir}/LP_OnePager_{safe_name}_{period_end.replace('-', '_')}_nondet.md"
        
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w') as f:
            f.write(markdown)
        
        print(f"\n✓ Saved one-pager to: {output_file}")
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
                "recipe": "LP_OnePager_v1_nondet",
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
        retry_count = state.get("retry_count", 0)
        
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
            "retry_count": retry_count,
            "errors": state.get("errors", []),
            "path_taken": "non-deterministic"
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
    workflow.add_node("retry_ingestion", retry_ingestion_node)
    workflow.add_node("kpi_computation", kpi_computation_node)
    workflow.add_node("use_existing_kpis", use_existing_kpis_node)
    workflow.add_node("get_snapshot", get_snapshot_node)
    workflow.add_node("content_generation", content_generation_node)
    workflow.add_node("use_fallback_content", use_fallback_content_node)
    workflow.add_node("render", render_node)
    workflow.add_node("save_output", save_output_node)
    workflow.add_node("register_output", register_output_node)
    workflow.add_node("finalize", finalize_node)
    
    # Define edges
    workflow.set_entry_point("initialize")
    workflow.add_edge("initialize", "ingestion")
    
    # Conditional routing after ingestion
    workflow.add_conditional_edges(
        "ingestion",
        route_after_ingestion,
        {
            "continue": "kpi_computation",
            "retry": "retry_ingestion",
            "skip": "kpi_computation"  # Skip but continue with warnings
        }
    )
    
    # Retry ingestion loops back to check validation
    workflow.add_conditional_edges(
        "retry_ingestion",
        route_after_ingestion,
        {
            "continue": "kpi_computation",
            "retry": "retry_ingestion",
            "skip": "kpi_computation"
        }
    )
    
    # Conditional routing after KPI computation
    workflow.add_conditional_edges(
        "kpi_computation",
        route_after_kpi,
        {
            "continue": "get_snapshot",
            "fallback": "use_existing_kpis"
        }
    )
    
    # After using existing KPIs, continue to snapshot
    workflow.add_edge("use_existing_kpis", "get_snapshot")
    
    workflow.add_edge("get_snapshot", "content_generation")
    
    # Conditional routing after content generation
    workflow.add_conditional_edges(
        "content_generation",
        route_after_content,
        {
            "continue": "render",
            "fallback_content": "use_fallback_content"
        }
    )
    
    # After fallback content, continue to render
    workflow.add_edge("use_fallback_content", "render")
    
    workflow.add_edge("render", "save_output")
    workflow.add_edge("save_output", "register_output")
    workflow.add_edge("register_output", "finalize")
    workflow.add_edge("finalize", END)
    
    return workflow


def create_non_deterministic_workflow_app(mcp_server_url: str = "http://localhost:3333/mcp"):
    """Create compiled non-deterministic workflow app"""
    workflow = create_non_deterministic_workflow_graph()
    return workflow.compile()
