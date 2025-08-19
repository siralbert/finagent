import logging
import asyncio
from typing import List
from contextlib import AsyncExitStack
from app.libs.types import GraphState
from app.libs.decorators import with_thought_callback, log_thought
from app.api_routes.mcp_servers import load_server_config

logger = logging.getLogger(__name__)

def get_mcp_servers() -> List[str]:
    server_configs = load_server_config()
    active_servers = [s["hostname"] for s in server_configs if s["isActive"]]
    
    if not active_servers:
        logger.warning("No active MCP servers found, falling back to default values")
        return [
            "http://localhost:8083/mcp",  # stock_market_server
            "http://localhost:8084/mcp",  # financial_analysis_server
            "http://localhost:8085/mcp",  # web_news_server
            "http://localhost:8089/mcp"   # word_generator_server
        ]
    
    return active_servers

@with_thought_callback(category="setup", node_name="Preparation")
async def prepare_financial_analysis(state: GraphState) -> GraphState:
    """Prepare analysis by setting up server URLs for Strands Agent"""
    logger.info("Preparing analysis context...")
    
    new_state = state.copy()
    session_id = new_state.get("session_id")
    

    server_urls = get_mcp_servers()
    new_state["server_urls"] = server_urls
    
    if "metadata" not in new_state:
        new_state["metadata"] = {}
    new_state["metadata"]["last_active_node"] = "prepare_analysis"
    
    log_thought(
        session_id=session_id,
        type="thought",
        category="setup",
        node="Preparation",
        content=f"Prepared {len(server_urls)} MCP server URLs for Strands Agent",
        technical_details={"servers": server_urls}
    )
    
    new_state["next"] = "strands_reasoning"
    
    return new_state
