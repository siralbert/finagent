from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from app.api_routes import thought_stream, mcp_servers, router, file_download
import os
import logging
import subprocess
import sys
from pathlib import Path

log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,  # Changed to INFO to see debug messages
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / "app.log"),
        logging.StreamHandler(sys.stdout)  
    ]
)
logger = logging.getLogger("app")
# Set specific loggers to INFO to see our debug messages
logging.getLogger('router_api').setLevel(logging.INFO)
logging.getLogger('thought_stream').setLevel(logging.INFO)
logging.getLogger('strands_reasoning').setLevel(logging.INFO)
logging.getLogger('graph').setLevel(logging.INFO)
# Keep these at WARNING to reduce noise
logging.getLogger('botocore').setLevel(logging.WARNING)
logging.getLogger('boto3').setLevel(logging.WARNING)

class HealthCheckFilter(logging.Filter):
    def filter(self, record):
        return 'health' not in record.getMessage().lower()
logger.addFilter(HealthCheckFilter())

mcp_processes = {}
workflow_graph = None

app = FastAPI(title="Financial Agent API")

# Include API routers
app.include_router(thought_stream.router, prefix="/api/financial")
app.include_router(mcp_servers.router, prefix="/api/mcp-servers", tags=["MCP Servers"])
app.include_router(router.router, prefix="/api/router", tags=["Router"])
app.include_router(file_download.router, prefix="/api/files", tags=["File Downloads"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.on_event("startup")
async def startup_event():
    global mcp_processes, workflow_graph
    logger.info("Starting application initialization")

    # Use dependency inversion to avoid circular imports
    import importlib
    graph_module = importlib.import_module('app.libs.graph')
    create_workflow_graph_func = getattr(graph_module, 'create_workflow_graph')
    workflow_graph = create_workflow_graph_func()
    logger.info("Workflow graph compiled successfully")

    current_dir = os.path.dirname(os.path.abspath(__file__))
    libs_dir = os.path.join(current_dir, "libs")
    servers = {
        'stock': {
            'path': os.path.join(libs_dir, "mcp-servers/stock_market_server.py"),
            'port': 8083
        },
        'finance': {
            'path': os.path.join(libs_dir, "mcp-servers/financial_analysis_server.py"),
            'port': 8084
        },
        'news': {
            'path': os.path.join(libs_dir, "mcp-servers/web_news_server.py"),
            'port': 8085
        },
        'word': {
            'path': os.path.join(libs_dir, "mcp-servers/word_generator.py"),
            'port': 8089
        }
    }

    for server_name, config in servers.items():
        try:
            logger.info(f"Starting {server_name} MCP server on port {config['port']}")
            process = subprocess.Popen(
                [sys.executable, config['path'], "--port", str(config['port'])],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            mcp_processes[server_name] = process
        except Exception as e:
            logger.error(f"Error starting {server_name} MCP server: {e}")

    logger.info("Application startup complete")

@app.on_event("shutdown")
async def shutdown_event():
    global mcp_processes
    logger.info("Shutting down MCP servers")

    for server_name, process in mcp_processes.items():
        if process:
            try:
                logger.info(f"Terminating {server_name} MCP server")
                process.terminate()
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                logger.warning(f"{server_name} server didn't terminate gracefully, forcing...")
                process.kill()

    logger.info("MCP servers shutdown complete")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
