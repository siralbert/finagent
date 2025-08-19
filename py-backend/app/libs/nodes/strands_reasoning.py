import logging
from typing import Dict, Any, List
from app.libs.types import GraphState
from app.libs.decorators import with_thought_callback, log_thought
from app.libs.conversation_memory import conversation_memory
from app.libs.prompts import FINANCIAL_SYSTEM_PROMPT
from app.libs.mcp_client_factory import create_mcp_clients, MCPClientContext
from strands.agent import Agent

logger = logging.getLogger("strands_reasoning")

@with_thought_callback(category="analysis", node_name="Strands Reasoning")
async def execute_financial_analysis(state: GraphState) -> GraphState:
    """LangGraph node to perform reasoning with Strands Agent"""
    logger.info("Performing reasoning with Strands Agent...")

    new_state = state.copy()
    query = new_state.get("extracted_text", "")
    session_id = new_state.get("session_id")
    model = new_state.get("model", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")
    server_urls = new_state.get("server_urls", [])
    stream_enabled = new_state.get("streaming_enabled", True)
    
    logger.info(f"Starting Strands reasoning for session: {session_id}")

    if "metadata" not in new_state:
        new_state["metadata"] = {}
    
    if "thought_history" not in new_state:
        new_state["thought_history"] = []
        
    try:
        # Get conversation history for context
        conversation_history = []
        if session_id:
            conv_data = conversation_memory.get_conversation_history(session_id)
            # Convert to simple string format for Strands Agent
            for msg in conv_data.get("messages", []):
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if isinstance(content, list):
                    # Extract text from content blocks
                    text_content = ""
                    for block in content:
                        if isinstance(block, dict) and "text" in block:
                            text_content += block["text"] + " "
                    content = text_content.strip()
                
                if content and role in ["user", "assistant"]:
                    conversation_history.append({"role": role, "content": [{"text": content}]})

        log_thought(
            session_id=session_id,
            type="thought",
            category="setup",
            node="Strands Reasoning",
            content=f"Loaded conversation history with {len(conversation_history)} messages"
        )

        # Initialize MCP clients using our factory utility
        mcp_clients = []
        all_tools = []
        
        try:
            mcp_clients, all_tools = await create_mcp_clients(server_urls)
            
            if mcp_clients:
                log_thought(
                    session_id=session_id,
                    type="thought",
                    category="setup",
                    node="Strands Reasoning",
                    content=f"Connected to {len(mcp_clients)} MCP servers with {len(all_tools)} total tools"
                )
            else:
                logger.warning("No MCP clients were successfully connected")
                log_thought(
                    session_id=session_id,
                    type="thought",
                    category="warning",
                    node="Strands Reasoning",
                    content="Failed to connect to any MCP servers. Agent will continue without MCP tools."
                )
            
        except Exception as e:
            logger.error(f"Failed to initialize MCP clients: {str(e)}")
            log_thought(
                session_id=session_id,
                type="thought",
                category="error",
                node="Strands Reasoning",
                content=f"Failed to initialize MCP clients, continuing without tools",
                technical_details={"error": str(e)}
            )

        # Create Strands agent with or without MCP tools based on availability
        if all_tools and mcp_clients:
            try:
                tool_names = [getattr(tool, 'tool_name', str(tool)) for tool in all_tools]
                logger.info(f"Available tools: {', '.join(tool_names[:5])}{'...' if len(tool_names) > 5 else ''}")
                
                # Use our new MCPClientContext for managing connections
                client_context = MCPClientContext(mcp_clients)
                with client_context:
                    # Create enhanced callback handler for streaming visibility
                    callback = create_enhanced_callback_handler(session_id)
                    tool_names = [getattr(tool, 'tool_name', str(tool)) for tool in all_tools]
                    logger.info(f"Configuring Strands agent with tools: {', '.join(tool_names)}")
                    
                    # Configure the Strands agent with proper tools and callbacks
                    agent = Agent(
                        model=model,
                        system_prompt=FINANCIAL_SYSTEM_PROMPT,
                        messages=conversation_history[-10:] if conversation_history else [],
                        tools=all_tools,
                        callback_handler=callback
                    )
                    
                    # Execute the agent with streaming support if enabled
                    if stream_enabled:
                        final_answer = ""
                        result = None
                        
                        # Process the agent execution as an async stream
                        async for event in agent.stream_async(query):
                            if "data" in event and isinstance(event["data"], str):
                                final_answer += event["data"]
                            if "message" in event:
                                result = event
                    else:
                        # Execute without streaming
                        final_answer = ""
                        result = None
                        
                        async for event in agent.stream_async(query):
                            if "data" in event and isinstance(event["data"], str):
                                final_answer += event["data"]
                            if "message" in event:
                                result = event
            except Exception as e:
                logger.error(f"Error executing Strands Agent with tools: {str(e)}")
                log_thought(
                    session_id=session_id,
                    type="thought",
                    category="error",
                    node="Strands Reasoning",
                    content=f"Error using MCP tools, falling back to no-tool mode",
                    technical_details={"error": str(e)}
                )
                # Fall back to no-tool mode
                callback = create_enhanced_callback_handler(session_id)
                agent = Agent(
                    model=model,
                    system_prompt=FINANCIAL_SYSTEM_PROMPT,
                    messages=conversation_history[-10:] if conversation_history else [],
                    callback_handler=callback
                )
                
                final_answer = ""
                result = None
                
                async for event in agent.stream_async(query):
                    if "data" in event and isinstance(event["data"], str):
                        final_answer += event["data"]
                    elif "message" in event:
                        result = event
                
        else:
            # Fallback to agent without MCP tools
            log_thought(
                session_id=session_id,
                type="thought",
                category="setup",
                node="Strands Reasoning",
                content="No MCP tools available, using basic Strands Agent"
            )
            
            callback = create_enhanced_callback_handler(session_id)
            agent = Agent(
                model=model,
                system_prompt=FINANCIAL_SYSTEM_PROMPT,
                messages=conversation_history[-10:] if conversation_history else [],
                callback_handler=callback
            )
            
            final_answer = ""
            result = None
            
            async for event in agent.stream_async(query):
                if "data" in event and isinstance(event["data"], str):
                    final_answer += event["data"]
                elif "message" in event:
                    result = event
        
        # Extract response text
        response_text = ""
        
        if final_answer and final_answer.strip():
            response_text = final_answer.strip()
        elif result and isinstance(result, dict) and "message" in result:
            message = result["message"]
            if isinstance(message, dict) and "content" in message:
                for content_block in message["content"]:
                    if isinstance(content_block, dict) and "text" in content_block:
                        response_text += content_block["text"]
            elif hasattr(message, "content"):
                for content_block in message.content:
                    if hasattr(content_block, "text"):
                        response_text += content_block.text
        
        if not response_text:
            response_text = "I've analyzed your request, but encountered an issue providing a complete response. Please try asking your question again or rephrasing it."

        # Save to conversation memory
        if session_id:
            conversation_memory.add_assistant_message(
                session_id,
                response_text,
                source="strands_agent"
            )

        log_thought(
            session_id=session_id,
            type="thought",
            category="result", 
            node="Answer",  
            content=response_text
        )
        
        new_state["thought_history"].append({
            "type": "thought",
            "category": "result", 
            "node": "Answer",     
            "content": response_text
        })

        new_state["answer"] = response_text
        new_state["next"] = "format_response"
        new_state["metadata"]["last_active_node"] = "strands_reasoning"
        
        if session_id:
            log_thought(
                session_id=session_id,
                type="complete",
                category="result",
                node="Completion",
                content="Analysis complete"
            )

    except Exception as e:
        logger.error(f"Error in Strands reasoning: {str(e)}")
        
        log_thought(
            session_id=session_id,
            type="thought",
            category="error",
            node="Strands Reasoning",
            content=f"Error occurred during Strands Agent execution: {str(e)}",
            technical_details={"error": str(e)}
        )
        
        # Add error to thought history
        error_thought = {
            "type": "thought",
            "category": "error", 
            "node": "Strands Reasoning",
            "content": "Error occurred during analysis",
            "technical_details": {"error": str(e)}
        }
        new_state["thought_history"].append(error_thought)
        
        new_state["answer"] = f"I encountered an error during analysis: {str(e)}"
        new_state["next"] = "format_response"
    
    return new_state


def create_enhanced_callback_handler(session_id = None):
    """Create a simplified callback handler for Strands Agent with minimal noise.
    
    Args:
        session_id: Optional session ID for thought streaming (can be None for stateless operation)
        
    Returns:
        A callback handler function for Strands Agent
    """
    
    def callback_handler(**kwargs):
        if not session_id:
            return
        
        # Tool execution notification
        if "message" in kwargs:
            message = kwargs["message"]
            if isinstance(message, dict) and message.get("role") == "assistant":
                content = message.get("content", [])
                
                # Check for tool use in content
                for content_item in content:
                    if isinstance(content_item, dict) and "toolUse" in content_item:
                        tool_use = content_item["toolUse"]
                        tool_name = tool_use.get("name", "unknown")
                        
                        log_thought(
                            session_id=session_id,
                            type="thought",
                            category="tool",
                            node="Tool Executor",
                            content=f"Executing tool: {tool_name}",
                            technical_details={"parameters": tool_use.get("input", {})}
                        )
            
            # Tool result notification  
            elif isinstance(message, dict) and message.get("role") == "user":
                content = message.get("content", [])
                
                # Look for toolResult in content
                for content_item in content:
                    if isinstance(content_item, dict) and "toolResult" in content_item:
                        tool_result = content_item["toolResult"]
                        tool_use_id = tool_result.get("toolUseId", "")
                        
                        # Extract result content
                        result_data = ""
                        result_content = tool_result.get("content", [])
                        if result_content and isinstance(result_content, list):
                            for result_item in result_content:
                                if isinstance(result_item, dict) and "text" in result_item:
                                    result_data = result_item["text"]
                                    break
                        
                        log_thought(
                            session_id=session_id,
                            type="thought", 
                            category="tool",
                            node="Tool Executor",
                            content="Tool completed successfully",
                            technical_details={
                                "tool_result": result_data,
                                "tool_use_id": tool_use_id
                            }
                        )
    
    return callback_handler
