# Non-Deterministic Workflow Demonstration

## Overview

This document demonstrates a **non-deterministic LangGraph workflow** that makes decisions and takes different paths based on validation results and agent decisions.

## Key Features

### Conditional Routing

The workflow uses `add_conditional_edges()` to route to different nodes based on state evaluation:

1. **After Ingestion**: Routes to `retry`, `continue`, or `skip` based on validation
2. **After KPI Computation**: Routes to `continue` or `fallback` based on results
3. **After Content Generation**: Routes to `continue` or `fallback_content` based on validation

### Decision Points

#### 1. Ingestion Validation → Retry Logic
```python
def route_after_ingestion(state: WorkflowState) -> Literal["continue", "retry", "skip"]:
    validation = state.get("ingestion_validation", {})
    retry_count = state.get("retry_count", 0)
    
    if not validation.get("passed", False):
        if retry_count < 2:  # Max 2 retries
            return "retry"
        else:
            return "skip"  # Continue with warnings
    return "continue"
```

**Path Taken**:
- ✅ **Validation passed** → Continue to KPI computation
- ⚠️ **Validation failed** → Retry ingestion (up to 2 times)
- ⚠️ **Max retries reached** → Skip with warnings

#### 2. KPI Validation → Fallback Logic
```python
def route_after_kpi(state: WorkflowState) -> Literal["continue", "fallback"]:
    validation = state.get("kpi_validation", {})
    
    if not validation.get("passed", False):
        created_count = len(state.get("kpi_results", {}).get("created", []))
        if created_count == 0:
            return "fallback"  # Use existing KPIs
    
    return "continue"
```

**Path Taken**:
- ✅ **KPIs computed successfully** → Continue to snapshot
- ⚠️ **No KPIs computed** → Use existing KPIs from database (fallback)

#### 3. Content Validation → Fallback Content
```python
def route_after_content(state: WorkflowState) -> Literal["continue", "fallback_content"]:
    validation = state.get("content_validation", {})
    
    if not validation.get("passed", False):
        thesis_count = len(state.get("bullets", {}).get("thesis", []))
        risks_count = len(state.get("bullets", {}).get("risks", []))
        
        if thesis_count == 0 or risks_count == 0:
            return "fallback_content"
    
    return "continue"
```

**Path Taken**:
- ✅ **Content generated successfully** → Continue to render
- ⚠️ **Content generation failed** → Use fallback content

## Workflow Graph

```
initialize
    ↓
ingestion ──┐
    ↓       │
  [validate]│
    ├─ continue → kpi_computation
    ├─ retry ────┘ (up to 2 retries)
    └─ skip ──────→ kpi_computation (with warnings)
    
kpi_computation ──┐
    ↓              │
  [validate]       │
    ├─ continue → get_snapshot
    └─ fallback ───┘ (use_existing_kpis)
    
get_snapshot
    ↓
content_generation ──┐
    ↓                 │
  [validate]          │
    ├─ continue → render
    └─ fallback_content ─┘ (use_fallback_content)
    
render → save_output → register_output → finalize
```

## Example Run

```
✓ MCP session initialized
📥 Ingestion Agent (Attempt 1)
  ✓ Ingested files...
  ⚠ Ingestion validation failed - routing to RETRY

🔄 Retrying ingestion with alternative strategy (Retry 1)
  ✓ Ingested files...
  ⚠ Ingestion validation failed - routing to RETRY

🔄 Retrying ingestion with alternative strategy (Retry 2)
  ⚠ Max retries reached - routing to SKIP (with warnings)

📊 KPI Computation Agent
  ✓ Computed KPIs: 4 KPIs created
  ✓ KPI validation passed - routing to CONTINUE

📋 Retrieving Golden Facts Snapshot
  ✓ Retrieved 160 approved KPIs

✍️ Content Generation Agent
  ✓ Generated 5 thesis bullets and 3 risks
  ✓ Content validation passed - routing to CONTINUE

🎨 Rendering One-Pager
  ✓ Generated one-pager markdown

Summary:
  Path Taken: non-deterministic
  Retry Count: 2
```

## Running the Demo

```bash
source venv/bin/activate
python demo_agent_workflow.py
```

## Benefits

1. **Adaptive Behavior**: Workflow adapts to failures and retries intelligently
2. **Resilience**: Fallback mechanisms ensure workflow completes even with partial failures
3. **Transparency**: Clear logging shows which path was taken and why
4. **Debugging**: Easy to trace execution path through conditional branches

## Comparison: Deterministic vs Non-Deterministic

### Deterministic Workflow (`demo_langgraph_workflow.py`)
- Fixed sequence: A → B → C → D
- No branching or retries
- Fails fast on errors

### Multi-Agent Workflow (`demo_agent_workflow.py`)
- Conditional routing: A → [B|C|D] based on validation
- Retry logic with limits
- Fallback mechanisms
- Continues with warnings

## Next Steps

- Add human-in-the-loop approval steps
- Implement parallel execution paths
- Add more sophisticated retry strategies (exponential backoff)
- Add LangSmith tracing for path visualization

