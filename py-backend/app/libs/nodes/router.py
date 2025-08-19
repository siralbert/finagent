import logging
from typing import Dict, Any
from app.libs.utils import extract_message_content, create_bedrock_client, prepare_messages_with_binary_data
from app.libs.types import GraphState
from app.libs.prompts import ROUTER_SYSTEM_PROMPT
from app.libs.conversation_memory import conversation_memory
from app.libs.decorators import with_thought_callback, log_thought

logger = logging.getLogger(__name__)

@with_thought_callback(category="analysis", node_name="Router")
def process_router(state: GraphState) -> GraphState:
    logger.info("Router preprocessing and routing...")

    new_state = state.copy()
    session_id = new_state.get("session_id")

    if "metadata" not in new_state:
        new_state["metadata"] = {}
        
    previous_routing = new_state.get("metadata", {}).get("previous_routing")
    logger.info(f"Processing request for session: {session_id}, previous routing: {previous_routing}")

    user_message = None
    for msg in reversed(new_state.get("messages", [])):
        if msg.get('role') == 'user':
            user_message = msg
            break
    
    if user_message:
        extracted_text, file_data = extract_message_content(user_message)
        new_state["extracted_text"] = extracted_text
        new_state["file_data"] = file_data
        
        if session_id:
            conversation_memory.ensure_session_exists(session_id)
            conversation_memory.add_user_message(session_id, extracted_text, file_data)

        # Log user question
        log_thought(
            session_id=session_id,
            type="question",
            category="user_input",
            node="User",
            content=extracted_text
        )

        if file_data:
            new_state["route_to"] = "process_file"
            new_state["metadata"]["file_detected"] = True
            new_state["metadata"]["previous_routing"] = "process_file" 

            log_thought(
                session_id=session_id,
                type="thought",
                category="analysis",
                node="Router",
                content=f"File detected. Routing directly to process_file."
            )
        else:
            new_state["route_to"] = "classify_request"
            new_state["metadata"]["file_detected"] = False
            new_state["metadata"]["previous_routing"] = "financial_analysis"
            
            log_thought(
                session_id=session_id,
                type="thought",
                category="analysis",
                node="Router",
                content=f"No file detected. Routing to LLM classifier to determine query type."
            )
    else:
        new_state["extracted_text"] = ""
        new_state["file_data"] = None
        new_state["route_to"] = "handle_chat"        
    
        log_thought(
            session_id=session_id,
            type="thought",
            category="analysis",
            node="Router",
            content=f"No valid user message found. Routing to direct response."
        )

    return new_state

@with_thought_callback(category="analysis", node_name="LLM Router")
def classify_request(state: GraphState) -> GraphState:
    logger.info("LLM Router: Classifying message content...")
    
    new_state = state.copy()
    session_id = new_state.get("session_id")
    extracted_text = new_state.get("extracted_text", "")
    model = new_state.get("model", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")
    region = new_state.get("region", "us-west-2")
    
    if "metadata" not in new_state:
        new_state["metadata"] = {}
    
    try:
        client = create_bedrock_client(region)
        
        api_messages = []
        if session_id:
            conversation_history = conversation_memory.get_conversation_history(session_id)
            api_messages = prepare_messages_with_binary_data(conversation_history["messages"])
            
            history_length = len(api_messages)
            log_thought(
                session_id=session_id,
                type="thought",
                category="memory",
                node="LLM Router",
                content=f"Using conversation context with {history_length} messages for routing decision"
            )
        else:
            api_messages = [{
                "role": "user",
                "content": [{"text": extracted_text or "Hello"}]
            }]
        
        system_message = [{"text": ROUTER_SYSTEM_PROMPT}]
        
        response = client.converse(
            modelId=model,
            messages=api_messages,
            system=system_message,
            inferenceConfig={
                "maxTokens": 10,
                "temperature": 0.1,
            }
        )
        
        response_text = ""
        if "output" in response and "message" in response["output"]:
            output_message = response["output"]["message"]
            if "content" in output_message:
                for content_item in output_message["content"]:
                    if "text" in content_item:
                        response_text += content_item["text"]
        
        response_text = response_text.strip().lower()
        logger.info(f"LLM classification: {response_text}")
        
        new_state["llm_classification"] = response_text
        
        if "document" in response_text:
            new_state["route_to"] = "document_task"
            new_state["metadata"]["previous_routing"] = "document_task"
            
            log_thought(
                session_id=session_id,
                type="thought",
                category="analysis",
                node="LLM Router",
                content=f"LLM classified query as document generation request. Routing to document task workflow."
            )
        elif "visualization" in response_text:
            new_state["route_to"] = "visualize_data"
            new_state["metadata"]["previous_routing"] = "visualize_data"
            
            log_thought(
                session_id=session_id,
                type="thought",
                category="analysis",
                node="LLM Router",
                content=f"LLM classified query as visualization request. Routing to visualization workflow."
            )
        elif "financial" in response_text:
            new_state["route_to"] = "financial_analysis"
            new_state["metadata"]["previous_routing"] = "financial_analysis"
            
            log_thought(
                session_id=session_id,
                type="thought",
                category="analysis",
                node="LLM Router",
                content=f"LLM classified query as financial. Routing to financial analysis workflow."
            )
        else:  
            new_state["route_to"] = "handle_chat"
            new_state["metadata"]["previous_routing"] = "handle_chat"
            
            log_thought(
                session_id=session_id,
                type="thought",
                category="analysis",
                node="LLM Router",
                content=f"LLM classified query as general conversation. Routing to chat handler."
            )
            
    except Exception as e:
        logger.error(f"Error in LLM classification: {str(e)}")
        new_state["route_to"] = "handle_chat"
        new_state["metadata"]["llm_classification_error"] = str(e)
        
        log_thought(
            session_id=session_id,
            type="thought",
            category="error",
            node="LLM Router",
            content=f"Error during classification. Defaulting to chat handler.",
            technical_details={"error": str(e)}
        )

    return new_state