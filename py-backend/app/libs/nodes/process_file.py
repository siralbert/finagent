import logging
import asyncio
from app.libs.types import GraphState 
from langgraph.graph import END
from app.libs.decorators import with_thought_callback, log_thought

logger = logging.getLogger(__name__)

@with_thought_callback(category="setup", node_name="FileProcessor")
async def process_file(state: GraphState) -> GraphState:  
    logger.info("Process File node: Processing file...")
    
    new_state = state.copy()
    file_data = new_state.get("file_data")
    session_id = new_state.get("session_id")

    if "metadata" not in new_state:
        new_state["metadata"] = {}

    log_thought(
        session_id=session_id,
        type="thought",
        category="setup",
        node="Preparation",
        content="Starting file processing"
    )
    
    await asyncio.sleep(1.0)

    return new_state