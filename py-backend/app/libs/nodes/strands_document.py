import logging
import asyncio
from typing import Dict, Any, Optional, List
from app.libs.types import GraphState
from app.libs.utils import create_bedrock_client, prepare_messages_with_binary_data
from app.libs.decorators import with_thought_callback, log_thought
from app.libs.conversation_memory import conversation_memory
from app.libs.mcp_client_factory import create_mcp_clients, MCPClientContext
from strands import Agent
from strands.models.bedrock import BedrockModel
from langgraph.graph import END

logger = logging.getLogger(__name__)

@with_thought_callback(category="document", node_name="Strands Document Agent")
async def execute_document_generation(state: GraphState) -> GraphState:
    """
    Use Strands agent with MCP tools for document processing tasks
    """
    logger.info("Strands Document Agent: Processing document generation request...")
    
    new_state = state.copy()
    query = new_state.get("extracted_text", "")
    session_id = new_state.get("session_id")
    
    if "metadata" not in new_state:
        new_state["metadata"] = {}
    new_state["metadata"]["last_active_node"] = "strands_document"
    
    try:
        log_thought(
            session_id=session_id,
            type="process",
            category="document_generation",
            node="Strands Document Agent",
            content="Initializing Strands agent with Word Generator tools"
        )
        
        # Initialize MCP clients for Word Generator
        word_server_urls = ["http://localhost:8089/mcp"]
        mcp_clients = []
        all_tools = []
        
        try:
            mcp_clients, all_tools = await create_mcp_clients(word_server_urls)
            
            if not mcp_clients or not all_tools:
                error_msg = "Word Generator service is not available. Please ensure the Word Generator MCP server is running."
                logger.error(error_msg)
                new_state["answer"] = error_msg
                return new_state
            
            tool_names = [getattr(tool, 'tool_name', str(tool)) for tool in all_tools]
            logger.info(f"Connected to Word Generator with {len(all_tools)} tools: {', '.join(tool_names)}")
            
        except Exception as e:
            error_msg = f"Failed to connect to Word Generator server: {str(e)}"
            logger.error(error_msg)
            new_state["answer"] = error_msg
            return new_state
        
        # Create the Strands agent
        model = BedrockModel(
            model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
            region="us-west-2"
        )
        
        # Use MCPClientContext for managing connections like in strands_reasoning
        client_context = MCPClientContext(mcp_clients)
        with client_context:
            agent = Agent(
                model=model,
                tools=all_tools,
                system_prompt="""You are a professional document generation assistant specializing in creating Word documents.

Your capabilities include:
- Creating formatted Word documents with headings, paragraphs, and bullet points
- Generating financial reports with structured data
- Creating documents with embedded charts and visualizations
- Converting text content into professionally formatted documents

When a user requests document generation:
1. Analyze their request to determine the document type and content
2. Use appropriate Word Generator tools to create the document
3. Provide clear feedback about the document creation process
4. Include download information when documents are successfully created

Always be helpful and provide detailed information about the documents you create."""
            )
            
            log_thought(
                session_id=session_id,
                type="thought",
                category="document_generation",
                node="Strands Document Agent",
                content=f"Strands agent configured with {len(all_tools)} Word Generator tools"
            )
            
            # Prepare conversation history for context
            conversation_context = ""
            if session_id:
                history = conversation_memory.get_conversation_history(session_id)
                recent_messages = history["messages"][-10:]  # Last 10 messages for context
                
                for msg in recent_messages:
                    role = msg.get('role', 'unknown')
                    content = msg.get('content', '')
                    if isinstance(content, list):
                        text_content = ' '.join([item.get('text', '') for item in content if isinstance(item, dict) and 'text' in item])
                    else:
                        text_content = str(content)
                    
                    if text_content.strip():
                        conversation_context += f"{role}: {text_content}\n"
            
            # Create enhanced prompt with context
            enhanced_query = f"""
Context from recent conversation:
{conversation_context}

Current document generation request:
{query}

Please analyze this request and create the appropriate document using the available Word Generator tools. 
Consider the conversation context to make the document more relevant and comprehensive.
"""
            
            log_thought(
                session_id=session_id,
                type="thought",
                category="document_generation",
                node="Strands Document Agent",
                content="Processing document generation request with conversation context"
            )
            
            # Run the Strands agent using streaming API
            final_answer = ""
            result = None
            reasoning_buffer = ""
            tool_results = []
            
            async for event in agent.stream_async(enhanced_query):
                if "data" in event and isinstance(event["data"], str):
                    final_answer += event["data"]
                    # Buffer reasoning data instead of sending immediately
                    if event["data"].strip():
                        reasoning_buffer += event["data"]
                elif "message" in event:
                    result = event
                    # Check if this is a tool result containing download link
                    message = event.get("message", {})
                    if isinstance(message, dict) and "content" in message:
                        for content_block in message["content"]:
                            if isinstance(content_block, dict) and "toolResult" in content_block:
                                tool_result = content_block["toolResult"]
                                result_content = tool_result.get("content", [])
                                for result_item in result_content:
                                    if isinstance(result_item, dict) and "text" in result_item:
                                        tool_text = result_item["text"]
                                        if "Download available at:" in tool_text:
                                            tool_results.append(tool_text)
            
            # Send the buffered reasoning as a single thought
            if reasoning_buffer.strip():
                log_thought(
                    session_id=session_id,
                    type="thought",
                    category="analysis",
                    node="Document Generation",
                    content=reasoning_buffer.strip()
                )
            
            # Extract response text
            if final_answer and final_answer.strip():
                response_text = final_answer.strip()
            elif result and isinstance(result, dict) and "message" in result:
                message = result["message"]
                response_text = ""
                if isinstance(message, dict) and "content" in message:
                    for content_block in message["content"]:
                        if isinstance(content_block, dict) and "text" in content_block:
                            response_text += content_block["text"]
                elif hasattr(message, "content"):
                    for content_block in message.content:
                        if hasattr(content_block, "text"):
                            response_text += content_block.text
            else:
                response_text = "Document generation completed, but no response was returned."
            
            # Add tool results with download links to response
            if tool_results:
                response_text += "\n\n" + "\n".join(tool_results)
            
            new_state["answer"] = response_text
            
            # Add to conversation memory
            if session_id:
                conversation_memory.add_assistant_message(
                    session_id,
                    response_text,
                    source="strands_document"
                )
            
            # Send final result thought for frontend to process - only this one, not the duplicate
            log_thought(
                session_id=session_id,
                type="thought",
                category="result",
                node="Answer",
                content=response_text
            )
        
        return new_state
        
    except Exception as e:
        error_msg = f"Error in Strands document processing: {str(e)}"
        logger.error(error_msg)
        new_state["answer"] = error_msg
        return new_state