import logging
from app.libs.utils import create_bedrock_client, prepare_messages_with_binary_data
from app.libs.types import GraphState  
from app.libs.prompts import CHAT_SYSTEM_PROMPT
from app.libs.conversation_memory import conversation_memory 
from app.libs.decorators import with_thought_callback, log_thought
from langgraph.graph import END

logger = logging.getLogger(__name__)

@with_thought_callback(category="analysis", node_name="DirectResponse")
def handle_chat(state: GraphState) -> GraphState:  
    logger.info("Direct Response node: Generating response...")
    
    new_state = state.copy()
    query = new_state.get("extracted_text", "")
    model = new_state.get("model")
    region = new_state.get("region")
    session_id = new_state.get("session_id")
    file_data = new_state.get("file_data")
    
    if "metadata" not in new_state:
        new_state["metadata"] = {}

    try:
        client = create_bedrock_client(region)

        api_messages = []
        if session_id:
            conversation_history = conversation_memory.get_conversation_history(session_id)
            api_messages = prepare_messages_with_binary_data(conversation_history["messages"])
        else:
            api_messages = [{
                "role": "user",
                "content": [{"text": query}]
            }]
        system_message = [{"text": CHAT_SYSTEM_PROMPT}]

        response = client.converse(
            modelId=model,
            messages=api_messages,
            system=system_message,
            inferenceConfig={
                "maxTokens": 2000,
                "temperature": 0.7,
            }
        )
        
        response_text = ""
        if "output" in response and "message" in response["output"]:
            output_message = response["output"]["message"]
            if "content" in output_message:
                for content_item in output_message["content"]:
                    if "text" in content_item:
                        response_text += content_item["text"]
        
        new_state["answer"] = response_text
        
        if session_id and response_text:
            conversation_memory.add_assistant_message(
                session_id, 
                response_text, 
                source="direct_response"
            )
        
        log_thought(
            session_id=session_id,
            type="thought",
            category="result",
            node="Answer",
            content=response_text
        )
    
    except Exception as e:
        logger.error(f"Error generating direct response: {str(e)}")
        error_message = f"I'm sorry, I encountered an error while processing your query: {str(e)}"
        new_state["answer"] = error_message
        
        if session_id:
            conversation_memory.add_assistant_message(
                session_id, 
                error_message, 
                source="direct_response_error"
            )
        
        log_thought(
            session_id=session_id,
            type="thought",
            category="error",  
            node="Reasoning",
            content=f"Error generating response: {str(e)}"
        )
    
    new_state["route_to"] = END
    return new_state