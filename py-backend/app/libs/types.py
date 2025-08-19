from typing import Dict, List, Literal, Optional, TypedDict, Any
from langgraph.graph import END

class GraphState(TypedDict, total=False):
    messages: List[Dict[str, Any]]
    route_to: Optional[Literal["file_processing", "direct_response", "financial_analysis", "llm_router", END, "prepare_analysis", "perform_reasoning", "tool_executor", "format_response"]]
    model: str
    model_id: str
    region: str
    file_data: Optional[Dict[str, Any]]
    extracted_text: str
    llm_classification: Optional[str]
    response: Optional[str]
    answer: Optional[str]
    metadata: Dict[str, Any]
    session_id: Optional[str]
    thought_callback: Optional[Any]
    action_groups: List[Dict[str, Any]]
    tool_server_mapping: Dict[str, str]
    query: str
    instruction: str
    server_urls: List[str]
    thought_history: List[Dict[str, Any]]
    analyzer: Any
    next: Optional[str]
    invocation_id: Optional[str]
    tool_result: Optional[Dict[str, Any]]
    tool_error: Optional[str]
    return_control_info: Optional[Dict[str, Any]]
    tool_execution: Optional[Dict[str, Any]]
