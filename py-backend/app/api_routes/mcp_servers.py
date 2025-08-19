from fastapi import APIRouter, HTTPException, Body
from typing import List, Dict, Optional, Any
import json
import os
import logging
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

# Path to store server configuration
MCP_SERVER_CONFIG_PATH = "mcp_server_config.json"

# Model for server information
class MCPServer(BaseModel):
    id: str
    name: str
    hostname: str
    isActive: bool
    isConnected: Optional[bool] = None

class ServerTestRequest(BaseModel):
    hostname: str

# Initial default values
DEFAULT_SERVERS = [
    {
        "id": "stock-market",
        "name": "Stock Market Server",
        "hostname": "http://localhost:8083/sse",
        "isActive": True,
        "isConnected": True
    },
    {
        "id": "financial-analysis",
        "name": "Financial Analysis Server",
        "hostname": "http://localhost:8084/sse",
        "isActive": True,
        "isConnected": True
    },
    {
        "id": "web-news",
        "name": "Web News Server",
        "hostname": "http://localhost:8085/sse",
        "isActive": True,
        "isConnected": True
    }
]

def load_server_config() -> List[Dict[str, Any]]:
    try:
        if os.path.exists(MCP_SERVER_CONFIG_PATH):
            with open(MCP_SERVER_CONFIG_PATH, "r") as f:
                return json.load(f)
        else:
            # Save default values if config file doesn't exist
            save_server_config(DEFAULT_SERVERS)
            return DEFAULT_SERVERS
    except Exception as e:
        logger.error(f"Error loading MCP server config: {e}")
        return DEFAULT_SERVERS

def save_server_config(servers: List[Dict[str, Any]]) -> None:
    try:
        with open(MCP_SERVER_CONFIG_PATH, "w") as f:
            json.dump(servers, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving MCP server config: {e}")

@router.get("/", response_model=List[MCPServer])
async def get_mcp_servers():
    """Returns the currently configured MCP server list."""
    return load_server_config()

@router.post("/", response_model=List[MCPServer])
async def update_mcp_servers(servers: List[MCPServer] = Body(...)):
    """Updates the MCP server list."""
    server_data = [server.dict() for server in servers]
    save_server_config(server_data)
    return server_data

@router.post("/test", response_model=Dict[str, Any])
async def test_mcp_server(request: ServerTestRequest = Body(...)):
    """Tests connection to a specific MCP server."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    import asyncio
    
    try:
        # Test server connection with 5 second timeout
        async with asyncio.timeout(5):
            async with streamablehttp_client(url=request.hostname) as (read_stream, write_stream, get_session_id):
                session = ClientSession(read_stream, write_stream)
                async with session as s:
                    await s.initialize()
                    # Test connection by fetching tools list
                    tools_result = await s.list_tools()
                    return {"success": True, "tools_count": len(tools_result.tools) if tools_result.tools else 0}
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"MCP server connection test failed: {e}")
        logger.error(f"Full error trace: {error_details}")
        return {"success": False, "error": str(e), "details": error_details}