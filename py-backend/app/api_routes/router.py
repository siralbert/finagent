from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from typing import List, Union, Dict, Any, Optional
from pydantic import BaseModel
from app.libs import get_or_create_clients, extract_message_content, process_messages_with_graph, thought_handler, create_workflow_graph, default_region
from app.libs.conversation_memory import conversation_memory
from app.libs.prompts import FINANCIAL_SYSTEM_PROMPT
import time
import random
import string
import logging

logger = logging.getLogger("router_api")
router = APIRouter()
class Message(BaseModel):
    role: str
    content: Union[str, List[Dict[str, Any]]]

class RouterRequest(BaseModel):
    messages: List[Message]
    model: str
    region: str
    fileData: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = None

@router.post("/")
async def route_request(request: Request, background_tasks: BackgroundTasks):
    try:
        logger.info("Router API request received - unified workflow")
        
        data = await request.json()
        messages = data.get("messages", [])
        model = data.get("model", "")
        region = data.get("region", "")
        client_session_id = data.get("session_id")
        
        if not messages or not isinstance(messages, list):
            raise HTTPException(status_code=400, detail="Messages are required and must be a non-empty array")
        if not model:
            raise HTTPException(status_code=400, detail="Model selection is required")
        if not region:
            raise HTTPException(status_code=400, detail="Region selection is required")
        
        from app.libs.utils import get_or_create_clients
        clients = get_or_create_clients(region)
        bedrock_agent_client = clients["bedrock_agent_client"]
        
        if client_session_id:
            if client_session_id in conversation_memory.conversations:
                session_id = client_session_id
                logger.info(f"Reusing session: {session_id}")
                
                # Ensure thought handler also has this session registered
                if client_session_id not in thought_handler.thought_store.queues:
                    thought_handler.register_session(session_id)
            else:
                logger.warning(f"Session {client_session_id} not found, creating new session")
                random_suffix = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(10))
                session_id = f"session-{int(time.time())}-{random_suffix}"
                logger.info(f"Created new session: {session_id}")
        else:
            random_suffix = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(10))
            session_id = f"session-{int(time.time())}-{random_suffix}"
            logger.info(f"Created new session: {session_id}")
        
        thought_handler.register_session(session_id)
        
        extracted_text = ""
        file_data = None
        
        for msg in reversed(messages):
            if msg.get('role') == 'user':
                extracted_text, file_data = extract_message_content(msg)
                break
        
        config = None 
        conversation_memory.ensure_session_exists(session_id)
        conversation_memory_state = conversation_memory.get_raw_conversation(session_id)
    
        metadata = conversation_memory_state.get("metadata", {}).copy() if conversation_memory_state else {}
        
        initial_state = {
            "messages": messages, 
            "route_to": None,
            "model": model,
            "region": region,
            "file_data": file_data,
            "extracted_text": extracted_text,
            "llm_classification": None,
            "response": None,
            "answer": None,
            "metadata": metadata,
            "session_id": session_id,
            "bedrock_session_id": session_id,
            "query": extracted_text,
            "model_id": model,
            "instruction": FINANCIAL_SYSTEM_PROMPT,
            "server_urls": metadata.get("server_urls", []),
            "action_groups": metadata.get("action_groups", []),
            "tool_server_mapping": metadata.get("tool_server_mapping", {}),
            "thought_history": metadata.get("thought_history", []),
            "analyzer": metadata.get("analyzer", None)
        }

        initial_response = {
            "name": "session_initiated",
            "input": {
                "answering_tool": "financial",
                "direct_answer": "processing",
                "session_id": session_id
            }
        }
        
        background_tasks.add_task(
            process_messages_background,
            state=initial_state,
            model=model,
            region=region,
            session_id=session_id,
            config=config
        )
        
        return initial_response
        
    except Exception as e:
        logger.error(f"Router API error: {str(e)}")
        logger.error(f"Full error details: {{'name': {type(e).__name__}, 'message': {str(e)}}}")
        
        if isinstance(e, HTTPException):
            raise e
        else:
            raise HTTPException(status_code=500, detail=str(e))


@router.get("/validate-session/{session_id}")
async def validate_session(session_id: str, request: Request):
    """Validate if a session exists and is still active"""
    try:
        if session_id in thought_handler.thought_store.queues:
            logger.info(f"Session validation: {session_id} is valid in thought store")
            return {"valid": True}
            
        try:
            region = request.query_params.get("region", "us-west-2") 
            clients = get_or_create_clients(region)
            bedrock_agent_client = clients["bedrock_agent_client"]
            
            response = bedrock_agent_client.get_session(sessionIdentifier=session_id)
            logger.info(f"Bedrock session {session_id} is valid")
            return {"valid": True}
        except Exception as e:
            logger.warning(f"Bedrock session validation failed: {e}")
            
        logger.info(f"Session validation: {session_id} is invalid")
        return {"valid": False}
    except Exception as e:
        logger.error(f"Error validating session: {e}")
        raise HTTPException(status_code=500, detail=f"Error validating session: {str(e)}")

async def process_messages_background(state, model, region, session_id, config):
    try:
        logger.info(f"Starting background processing for session {session_id}")
        
        from app.libs import process_messages_with_graph
        try:
            result = await process_messages_with_graph(
                state=state,
                model=model,
                region=region, 
                session_id=session_id,
                config=config
            )
            
            from app.libs import thought_handler
            complete_thought = {
                "type": "complete",
                "content": result.get("input", {}).get("direct_answer", "Analysis complete"),
                "node": "Completion"
            }
            thought_handler.thought_store.add_thought(session_id, complete_thought)
        except Exception as e:
            logger.error(f"Error in process_messages_with_graph: {e}", exc_info=True)
            from app.libs import thought_handler
            error_thought = {
                "type": "error",
                "content": f"Error processing request: {str(e)}",
                "node": "Error"
            }
            thought_handler.thought_store.add_thought(session_id, error_thought)
        
        logger.info(f"Background processing completed for session {session_id}")
        
        # DON'T mark session complete - let SSE stream stay alive for continuous use
        # This preserves the original behavior where sessions stayed active
    except Exception as e:
        logger.error(f"Error in background processing for {session_id}: {str(e)}", exc_info=True)
        error_thought = {
            "type": "error",
            "content": f"Processing error: {str(e)}",
            "node": "Error"
        }
        thought_handler.thought_store.add_thought(session_id, error_thought)
