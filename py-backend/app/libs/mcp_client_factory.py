import logging
from typing import Dict, List, Any, Tuple, Callable, Optional
from contextlib import ExitStack
from mcp.client.streamable_http import streamablehttp_client
from strands.tools.mcp.mcp_client import MCPClient

logger = logging.getLogger(__name__)

async def create_mcp_clients(server_urls: List[str]) -> Tuple[List[MCPClient], List[Any]]:
    """
    Create MCP clients and collect tools from multiple MCP servers.
    
    Args:
        server_urls: List of MCP server URLs to connect to
        
    Returns:
        Tuple containing:
        - List of connected MCPClient objects
        - List of all tools collected from the servers
    """
    all_tools = []
    mcp_clients = []
    
    for url in server_urls:
        try:
            # Create transport function with proper error handling
            def create_transport(url=url):
                try:
                    logger.info(f"Creating transport for MCP server: {url}")
                    return streamablehttp_client(url)
                except Exception as e:
                    logger.error(f"Transport error for {url}: {str(e)}")
                    raise
            
            # Create MCP client
            logger.info(f"Initializing MCP client for {url}")
            mcp_client = MCPClient(create_transport)
            
            # We're going to safely test the connection first
            try:
                with mcp_client:
                    logger.info(f"Testing connection to MCP server {url}")
                    tools = mcp_client.list_tools_sync()
                    
                    if tools:
                        tool_names = [getattr(tool, 'tool_name', str(tool)) for tool in tools]
                        logger.info(f"Found tools at {url}: {', '.join(tool_names[:5])}{'...' if len(tool_names) > 5 else ''}")
                        
                        all_tools.extend(tools)
                        mcp_clients.append(mcp_client)
                        logger.info(f"Successfully connected to MCP server {url}, found {len(tools)} tools")
                    else:
                        logger.warning(f"Connected to MCP server {url}, but no tools were found")
            except Exception as e:
                logger.error(f"MCP client initialization failed for {url}: {str(e)}")
                continue 

        except Exception as e:
            logger.error(f"Failed to connect to MCP server {url}: {str(e)}")
    
    return mcp_clients, all_tools

class MCPClientContext:
    """Context manager for handling multiple MCP clients."""
    
    def __init__(self, clients: List[MCPClient]):
        """
        Initialize with a list of MCP clients.
        
        Args:
            clients: List of MCPClient objects to manage
        """
        self.clients = clients
        self.stack = ExitStack()
    
    def __enter__(self):
        """Enter the context, managing all client connections."""
        for client in self.clients:
            self.stack.enter_context(client)
        return self
    
    def __exit__(self, *args):
        """Exit the context, closing all client connections."""
        self.stack.close()
    
    @property
    def is_empty(self):
        """Check if there are any clients."""
        return len(self.clients) == 0

def get_mcp_server_urls_from_config(config: Dict[str, Any]) -> List[str]:
    """
    Extract MCP server URLs from configuration.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        List of MCP server URLs
    """
    servers = []
    if not config:
        return servers
        
    mcp_servers = config.get("mcp_servers", [])
    for server in mcp_servers:
        if "host" in server and "port" in server:
            protocol = server.get("protocol", "http")
            host = server["host"]
            port = server["port"]
            servers.append(f"{protocol}://{host}:{port}")
    
    return servers

# Server name to URL mapping
SERVER_NAME_TO_URL = {
    "word": "http://localhost:8089/mcp",
    "stock": "http://localhost:8083/mcp", 
    "financial": "http://localhost:8084/mcp",
    "news": "http://localhost:8085/mcp"
}

def get_mcp_client(server_name: str) -> Optional[MCPClient]:
    """
    Get an MCP client for a specific server.
    
    Args:
        server_name: Name of the server (word, stock, financial, news)
        
    Returns:
        MCPClient instance or None if connection fails
    """
    url = SERVER_NAME_TO_URL.get(server_name)
    if not url:
        logger.error(f"Unknown server name: {server_name}")
        return None
    
    try:
        def create_transport():
            logger.info(f"Creating transport for MCP server: {url}")
            return streamablehttp_client(url)
        
        logger.info(f"Initializing MCP client for {server_name} at {url}")
        mcp_client = MCPClient(create_transport)
        
        # Test connection
        with mcp_client:
            tools = mcp_client.list_tools_sync()
            if tools:
                logger.info(f"Successfully connected to {server_name} server, found {len(tools)} tools")
                return mcp_client
            else:
                logger.warning(f"Connected to {server_name} server but no tools found")
                return None
                
    except Exception as e:
        logger.error(f"Failed to connect to {server_name} server at {url}: {str(e)}")
        return None

def get_all_available_tools() -> List[Dict[str, Any]]:
    """
    Get information about all available tools from all servers.
    
    Returns:
        List of tool information dictionaries
    """
    all_tools = []
    
    for server_name, url in SERVER_NAME_TO_URL.items():
        try:
            def create_transport():
                return streamablehttp_client(url)
            
            mcp_client = MCPClient(create_transport)
            
            with mcp_client:
                tools = mcp_client.list_tools_sync()
                for tool in tools:
                    tool_info = {
                        'server_name': server_name,
                        'url': url,
                        'name': getattr(tool, 'tool_name', str(tool)),
                        'description': getattr(tool, 'description', '')
                    }
                    all_tools.append(tool_info)
                    
        except Exception as e:
            logger.warning(f"Could not connect to {server_name} server: {str(e)}")
            continue
    
    return all_tools