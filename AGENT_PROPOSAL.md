# Proposal: Adding AI Agents to LP One-Pager Demo

## Executive Summary

This proposal outlines adding AI agents to automate and enhance the LP one-pager generation workflow. Agents will orchestrate MCP tools, make intelligent decisions about data processing, and handle error recovery—transforming the current scripted demo into an intelligent, adaptive system.

## Current State

The demo currently uses a **shell script** (`demo_full_workflow.sh`) that:
- Calls MCP tools sequentially via `curl`
- Has fixed, predefined steps
- Requires manual intervention for errors
- Cannot adapt to different data sources or formats
- Cannot make decisions about what data to ingest or how to process it

## Proposed Agent Architecture

### Agent Roles

#### 1. **Data Ingestion Agent** (Primary)
- **Role**: Orchestrates data ingestion from multiple sources
- **Responsibilities**:
  - Detects available data files in `/data` directory
  - Determines file types and selects appropriate ingestion tools
  - Handles missing files gracefully (generate, skip, or prompt)
  - Validates ingestion results
  - Retries on failures with different strategies

#### 2. **KPI Computation Agent** (Secondary)
- **Role**: Validates and computes KPIs intelligently
- **Responsibilities**:
  - Reviews ingested data quality
  - Determines optimal KPI computation parameters
  - Validates computed KPIs against expected ranges
  - Handles edge cases (missing data, outliers)

#### 3. **Content Generation Agent** (Tertiary)
- **Role**: Generates narrative content for one-pager
- **Responsibilities**:
  - Analyzes KPI trends and generates investment thesis
  - Identifies key risks from memo content
  - Ensures narrative matches financial data
  - Validates output quality before rendering

### Agent Interaction Flow

```
┌─────────────────┐
│  Orchestrator   │
│     Agent       │
└────────┬────────┘
         │
         ├──> Ingestion Agent ──> MCP Tools (ingest_*)
         │
         ├──> KPI Agent ──────────> MCP Tools (compute_kpis)
         │
         └──> Content Agent ───────> MCP Tools (render_*)
```

## Framework Recommendations

### Option 1: **LangChain + LangGraph** ⭐ Recommended

**Why LangChain/LangGraph:**
- ✅ **Excellent MCP Integration**: Native support for MCP tools via `@langchain/mcp`
- ✅ **State Management**: LangGraph provides explicit state management for complex workflows
- ✅ **Error Handling**: Built-in retry and fallback mechanisms
- ✅ **Observability**: LangSmith integration for monitoring and debugging
- ✅ **Mature Ecosystem**: Large community, extensive documentation
- ✅ **Tool Calling**: Native support for structured tool calling with LLMs

**Architecture:**
```python
# Pseudo-code structure
from langchain_mcp import McpTool
from langgraph.graph import StateGraph

# Define agents as nodes in a graph
graph = StateGraph()
graph.add_node("ingestion_agent", ingestion_agent)
graph.add_node("computation_agent", computation_agent)
graph.add_node("generation_agent", generation_agent)
graph.add_edge("ingestion_agent", "computation_agent")
graph.add_edge("computation_agent", "generation_agent")
```

**Pros:**
- Best integration with MCP protocol
- Explicit workflow control
- Strong debugging tools
- Production-ready

**Cons:**
- Steeper learning curve
- More boilerplate code

---

### Option 2: **CrewAI**

**Why CrewAI:**
- ✅ **Role-Based Agents**: Natural fit for our multi-agent architecture
- ✅ **Easy Configuration**: Simple YAML-based agent definitions
- ✅ **Built-in Collaboration**: Agents can share information and collaborate
- ✅ **Task Delegation**: Easy to assign tasks to specialized agents

**Architecture:**
```python
from crewai import Agent, Task, Crew

# Define specialized agents
ingestion_agent = Agent(
    role="Data Ingestion Specialist",
    goal="Ingest all available data sources",
    backstory="Expert at handling financial data files"
)

computation_agent = Agent(
    role="Financial Analyst",
    goal="Compute accurate KPIs",
    backstory="CFA-certified analyst with deep KPI expertise"
)
```

**Pros:**
- Intuitive agent definitions
- Built-in collaboration patterns
- Good for multi-agent scenarios

**Cons:**
- Less direct MCP integration (would need custom tools)
- Newer framework (less mature)
- Primarily Python-focused

---

### Option 3: **AutoGen (Microsoft)**

**Why AutoGen:**
- ✅ **Multi-Agent Conversations**: Excellent for agent-to-agent communication
- ✅ **Code Execution**: Built-in code execution capabilities
- ✅ **Human-in-the-Loop**: Easy to add human approval steps
- ✅ **Customizable**: Highly configurable agent behaviors

**Pros:**
- Strong multi-agent communication
- Good for complex workflows
- Microsoft-backed (stable)

**Cons:**
- MCP integration would require custom implementation
- More complex setup
- Primarily research-focused

---

### Option 4: **Simple Custom Agent (TypeScript/Node.js)**

**Why Custom:**
- ✅ **Full Control**: Complete control over agent logic
- ✅ **Type Safety**: TypeScript provides type safety
- ✅ **Direct MCP Calls**: Can use existing MCP client libraries
- ✅ **No Dependencies**: Minimal external dependencies

**Pros:**
- No framework overhead
- Direct integration with existing codebase
- Type-safe

**Cons:**
- Must build agent logic from scratch
- No built-in retry/error handling
- More development time

---

## Recommended Approach: **LangChain + LangGraph**

### Rationale

1. **MCP Native Support**: LangChain has official MCP tool integration (`@langchain/mcp`)
2. **Workflow Control**: LangGraph provides explicit state management perfect for our multi-step workflow
3. **Production Ready**: Mature framework with production deployments
4. **Observability**: LangSmith provides excellent debugging and monitoring
5. **Community**: Large community and extensive documentation

### Implementation Plan

#### Phase 1: Basic Agent (1-2 days)
- Single orchestrator agent that calls MCP tools
- Replace shell script with Python agent
- Basic error handling and retries

#### Phase 2: Multi-Agent System (3-5 days)
- Separate agents for ingestion, computation, and generation
- Agent-to-agent communication
- Intelligent decision-making

#### Phase 3: Advanced Features (5-7 days)
- Adaptive data discovery
- Quality validation
- Human-in-the-loop approvals
- LangSmith monitoring

## Proposed Agent Implementation

### Agent 1: Data Ingestion Agent

```python
from langchain_mcp import McpTool
from langgraph.graph import StateGraph
from langchain_openai import ChatOpenAI

class IngestionAgent:
    """Agent responsible for ingesting data from multiple sources."""
    
    def __init__(self, mcp_client):
        self.llm = ChatOpenAI(model="gpt-4")
        self.tools = [
            McpTool(name="ingest_excel", mcp_client=mcp_client),
            McpTool(name="ingest_csv", mcp_client=mcp_client),
            McpTool(name="ingest_memo", mcp_client=mcp_client),
            McpTool(name="ingest_edgar_xbrl", mcp_client=mcp_client),
        ]
        self.agent = self.llm.bind_tools(self.tools)
    
    async def ingest_all(self, deal_id: str, data_dir: str):
        """Intelligently ingest all available data sources."""
        # 1. Discover available files
        files = self.discover_files(data_dir)
        
        # 2. Determine ingestion strategy
        strategy = self.llm.invoke(f"""
            Analyze these files and determine ingestion order:
            {files}
            
            Return a JSON plan with file paths and tool names.
        """)
        
        # 3. Execute ingestion with error handling
        for file_info in strategy:
            try:
                result = await self.ingest_file(file_info, deal_id)
                if not result.success:
                    # Retry with different parameters
                    result = await self.retry_ingestion(file_info, deal_id)
            except Exception as e:
                # Log error and continue with next file
                self.handle_error(file_info, e)
```

### Agent 2: KPI Computation Agent

```python
class KPIComputationAgent:
    """Agent responsible for computing and validating KPIs."""
    
    async def compute_kpis(self, deal_id: str):
        """Compute KPIs with validation."""
        # 1. Check data quality
        quality = await self.validate_data_quality(deal_id)
        
        # 2. Determine computation parameters
        params = self.determine_parameters(quality)
        
        # 3. Compute KPIs
        result = await self.call_mcp_tool("compute_kpis", {
            "deal_id": deal_id,
            **params
        })
        
        # 4. Validate results
        validation = await self.validate_kpis(result)
        if not validation.passed:
            # Adjust and recompute
            return await self.recompute_with_adjustments(deal_id, validation)
        
        return result
```

### Agent 3: Content Generation Agent

```python
class ContentGenerationAgent:
    """Agent responsible for generating narrative content."""
    
    async def generate_content(self, deal_id: str, snapshot: dict):
        """Generate investment thesis and risks."""
        # 1. Analyze financial trends
        trends = self.analyze_trends(snapshot)
        
        # 2. Extract insights from memo (using vector search)
        memo_insights = await self.search_memo(deal_id, trends)
        
        # 3. Generate thesis bullets
        thesis = self.llm.invoke(f"""
            Generate 3-5 investment thesis bullets based on:
            Financials: {snapshot}
            Trends: {trends}
            Memo insights: {memo_insights}
        """)
        
        # 4. Generate risk bullets
        risks = self.llm.invoke(f"""
            Generate 3-5 key risks with mitigants based on:
            Financials: {snapshot}
            Memo insights: {memo_insights}
        """)
        
        return {"thesis": thesis, "risks": risks}
```

## Integration with Existing System

### MCP Tool Integration

```python
from langchain_mcp import McpTool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Initialize MCP client
async with stdio_client(StdioServerParameters(...)) as (read, write):
    async with ClientSession(read, write) as session:
        # Initialize session
        await session.initialize()
        
        # Create LangChain tools from MCP tools
        tools = []
        tools_list = await session.list_tools()
        for tool in tools_list.tools:
            mcp_tool = McpTool(name=tool.name, mcp_client=session)
            tools.append(mcp_tool)
```

### Workflow Graph

```python
from langgraph.graph import StateGraph, END
from typing import TypedDict

class WorkflowState(TypedDict):
    deal_id: str
    ingested_files: list[str]
    kpis_computed: bool
    snapshot: dict
    content: dict
    output_file: str

# Define workflow graph
workflow = StateGraph(WorkflowState)

# Add nodes
workflow.add_node("ingestion", ingestion_agent.ingest_all)
workflow.add_node("computation", computation_agent.compute_kpis)
workflow.add_node("generation", generation_agent.generate_content)
workflow.add_node("rendering", render_agent.render_onepager)

# Define edges
workflow.set_entry_point("ingestion")
workflow.add_edge("ingestion", "computation")
workflow.add_edge("computation", "generation")
workflow.add_edge("generation", "rendering")
workflow.add_edge("rendering", END)

# Compile and run
app = workflow.compile()
result = await app.ainvoke({
    "deal_id": "00000000-0000-0000-0000-000000000001",
    "data_dir": "./data"
})
```

## Use Cases Enabled by Agents

### 1. **Adaptive Data Discovery**
- Agent discovers available files automatically
- Determines file types and selects appropriate tools
- Handles missing files gracefully

### 2. **Intelligent Error Recovery**
- Retries failed operations with different parameters
- Falls back to alternative data sources
- Provides human-readable error messages

### 3. **Quality Validation**
- Validates data quality before processing
- Checks for outliers or anomalies
- Suggests corrections or warnings

### 4. **Dynamic Content Generation**
- Generates investment thesis based on actual financial trends
- Identifies risks from memo content using vector search
- Ensures narrative matches financial data

### 5. **Multi-Deal Processing**
- Processes multiple deals in parallel
- Tracks progress and handles errors per deal
- Generates comparative reports

## Implementation Timeline

### Week 1: Foundation
- **Day 1-2**: Set up LangChain + LangGraph environment
- **Day 3-4**: Implement MCP tool integration
- **Day 5**: Create basic orchestrator agent

### Week 2: Multi-Agent System
- **Day 1-2**: Implement Ingestion Agent
- **Day 3-4**: Implement KPI Computation Agent
- **Day 5**: Implement Content Generation Agent

### Week 3: Advanced Features
- **Day 1-2**: Add error handling and retries
- **Day 3-4**: Implement quality validation
- **Day 5**: Add LangSmith monitoring

### Week 4: Testing & Documentation
- **Day 1-3**: Comprehensive testing
- **Day 4-5**: Documentation and demo preparation

## Dependencies

### Python Packages
```txt
langchain>=0.1.0
langchain-openai>=0.1.0
langgraph>=0.1.0
@langchain/mcp>=0.1.0  # MCP integration
mcp>=1.0.0  # MCP client library
python-dotenv>=1.0.0
```

### Node.js (Existing)
- No changes needed to MCP server
- Agents call existing MCP tools via HTTP

## Demo Script Update

Replace `demo_full_workflow.sh` with:

```python
# demo_agent_workflow.py
import asyncio
from agents import OrchestratorAgent

async def main():
    agent = OrchestratorAgent()
    result = await agent.run_workflow(
        deal_id="00000000-0000-0000-0000-000000000001",
        data_dir="./data",
        company_name="Acme Software, Inc.",
        period_end="2025-09-30"
    )
    print(f"✅ One-pager generated: {result.output_file}")

if __name__ == "__main__":
    asyncio.run(main())
```

## Benefits

1. **Intelligence**: Agents make decisions, not just execute scripts
2. **Adaptability**: Handle different data sources and formats
3. **Reliability**: Better error handling and recovery
4. **Observability**: LangSmith provides detailed logs and traces
5. **Extensibility**: Easy to add new agents or capabilities
6. **User Experience**: More natural interaction (can ask questions, get explanations)

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Framework complexity | Start with simple agent, gradually add complexity |
| MCP integration issues | Use official LangChain MCP tools |
| Cost of LLM calls | Use cheaper models for simple tasks, cache results |
| Debugging difficulty | Use LangSmith for observability |

## Success Metrics

- **Reliability**: 95%+ success rate without manual intervention
- **Speed**: Complete workflow in < 2 minutes
- **Intelligence**: Correctly handles 90%+ of edge cases automatically
- **User Satisfaction**: Agents provide useful insights and explanations

## Next Steps

1. **Approve Framework**: Select LangChain + LangGraph (recommended)
2. **Set Up Environment**: Install dependencies and create agent directory
3. **Implement Phase 1**: Basic orchestrator agent
4. **Test & Iterate**: Validate with current demo data
5. **Expand**: Add specialized agents and advanced features

---

## Alternative: Quick Win with Simple Agent

If full LangChain implementation is too complex, we can start with a **simple Python agent** using:
- `openai` Python SDK for LLM calls
- Direct MCP HTTP calls (like current shell script)
- Simple decision-making logic

This would provide:
- ✅ Intelligent decision-making
- ✅ Error recovery
- ✅ Natural language interactions
- ✅ Minimal new dependencies

**Time**: 1-2 days vs 2-3 weeks for full LangChain implementation

---

**Prepared by**: AI Assistant  
**Date**: $(date)  
**Status**: Proposal - Awaiting Approval

