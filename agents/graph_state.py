"""
LangGraph State Definition for LP One-Pager Workflow
"""

from typing import TypedDict, List, Dict, Any, Optional
from typing_extensions import Annotated


class WorkflowState(TypedDict):
    """State managed by LangGraph workflow"""
    
    # Input parameters
    deal_id: str
    company_name: str
    period_end: str
    data_dir: str
    mcp_server_url: str  # Add this for workflow initialization
    
    # Workflow state
    mcp_caller: Optional[Any]  # McpToolCaller instance
    session_id: Optional[str]
    
    # Step results
    discovered_files: Dict[str, List[str]]
    ingestion_results: Dict[str, Any]
    kpi_results: Dict[str, Any]
    snapshot: List[Dict[str, Any]]
    bullets: Dict[str, List[str]]
    markdown: str
    output_file: Optional[str]
    
    # Error handling
    errors: Annotated[List[str], lambda x, y: x + y]  # Accumulate errors
    retry_count: int
    
    # Final result
    success: bool
    summary: Dict[str, Any]

