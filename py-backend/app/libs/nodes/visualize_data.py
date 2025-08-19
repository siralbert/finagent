import logging
import json
import base64
import asyncio
from botocore.exceptions import ClientError
from typing import Dict, Any, Optional
from app.libs.types import GraphState
from app.libs.utils import create_bedrock_client, prepare_messages_with_binary_data
from app.libs.decorators import with_thought_callback, log_thought
from app.libs.conversation_memory import conversation_memory
from app.libs.prompts import VISUALIZATION_SYSTEM_PROMPT
from langgraph.graph import END

logger = logging.getLogger(__name__)

@with_thought_callback(category="visualization", node_name="Visualization")
async def create_visualization(state: GraphState) -> GraphState:
    logger.info("Visualization node: Generating chart data...")
    
    new_state = state.copy()
    query = new_state.get("extracted_text", "")
    model = new_state.get("model")
    region = new_state.get("region")
    session_id = new_state.get("session_id")
    file_data = new_state.get("file_data")  

    if "metadata" not in new_state:
        new_state["metadata"] = {}
    new_state["metadata"]["last_active_node"] = "visualize_data"
    
    # Initialize retry tracking
    retry_count = new_state["metadata"].get("visualization_retry_count", 0)
    max_retries = 2  # Allow up to 2 retries (3 total attempts)
    previous_error = new_state["metadata"].get("visualization_error", "")
    
    processed_messages = []
    if session_id:
        messages_from_memory = conversation_memory.get_conversation_history(session_id)["messages"]
        processed_messages = prepare_messages_with_binary_data(messages_from_memory)
    else:
        processed_messages = [{
            "role": "user",
            "content": [{"text": query or "Please visualize this data"}]
        }]
    
    try:
        # Log retry status if applicable
        if retry_count > 0:
            log_thought(
                session_id=session_id,
                type="thought",
                category="analysis", 
                node="Visualization",
                content=f"Retrying visualization generation (attempt {retry_count + 1}/{max_retries + 1}). Previous error: {previous_error}"
            )
        else:
            log_thought(
                session_id=session_id,
                type="thought",
                category="analysis", 
                node="Visualization",
                content="Creating visualizations from your data."
            )
        await asyncio.sleep(1.0)
        
        client = create_bedrock_client(region)
        
        # Enhance system prompt with error context if retrying
        enhanced_prompt = VISUALIZATION_SYSTEM_PROMPT
        if retry_count > 0 and previous_error:
            enhanced_prompt += f"\n\nIMPORTANT: This is a retry attempt. The previous attempt failed with this error: {previous_error}\nPlease ensure the JSON output is properly formatted and follows the exact schema requirements. Pay special attention to:\n- Proper JSON syntax with matching braces and quotes\n- All required fields are present\n- Data array is properly structured\n- ChartConfig object is correctly formatted"
        
        system_prompt = [{
            "text": enhanced_prompt
        }]
        
        # Direct conversation without tools
        response = client.converse(
            modelId=model,
            messages=processed_messages,
            system=system_prompt,
        )
        
        # Extract response text
        response_text = ""
        if "output" in response and "message" in response["output"]:
            output_message = response["output"]["message"]
            if "content" in output_message:
                for content_item in output_message["content"]:
                    if "text" in content_item:
                        response_text += content_item["text"]
        
        # Extract JSON from response
        json_data = None
        image_analysis = None
        chart_data = None
        
        # Extract JSON using regex pattern
        import re
        json_pattern = r"```json\s*([\s\S]*?)\s*```"
        json_matches = re.findall(json_pattern, response_text)
        
        if json_matches:
            try:
                json_str = json_matches[0]
                chart_data = json.loads(json_str)
                
                # Extract image analysis if present
                if "imageAnalysis" in chart_data:
                    image_analysis = chart_data.get("imageAnalysis")
                    if image_analysis and isinstance(image_analysis, str) and image_analysis.strip():
                        log_thought(
                            session_id=session_id,
                            type="thought",
                            category="image_analysis",
                            node="Visualization",
                            content=f"{image_analysis}"
                        )
                        
                        # Store image analysis in metadata
                        new_state["metadata"]["image_analysis"] = image_analysis
                
                # Process special chart types (like pie)
                if chart_data.get("chartType") == "pie":
                    value_key = list(chart_data["chartConfig"].keys())[0]
                    segment_key = chart_data["config"].get("xAxisKey", "segment")
                    
                    chart_data["data"] = [{
                        "segment": item.get(segment_key, item.get("segment", item.get("category", item.get("name", "")))),
                        "value": item.get(value_key, item.get("value", 0))
                    } for item in chart_data["data"]]
                    
                    chart_data["config"]["xAxisKey"] = "segment"
                
                # Process chart config with colors (if not already processed)
                processed_chart_config = {}
                for i, (key, config) in enumerate(chart_data["chartConfig"].items()):
                    if isinstance(config, dict):
                        if "color" not in config:
                            config["color"] = f"hsl(var(--chart-{i + 1}))"
                        processed_chart_config[key] = config
                    else:
                        processed_chart_config[key] = {
                            "label": config,
                            "color": f"hsl(var(--chart-{i + 1}))"
                        }
                
                chart_data["chartConfig"] = processed_chart_config
                
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing JSON from response: {str(e)}")
                raise ValueError(f"JSON parsing error: {str(e)}. JSON content: {json_str[:200]}...")
        else:
            raise ValueError("No JSON data found in the response. Please ensure the response contains a properly formatted JSON block enclosed in ```json and ``` markers.")
        
        # Clean up response text by removing the JSON block
        response_text = re.sub(json_pattern, "", response_text).strip()
        if not response_text:
            response_text = "Here's the visualization based on the data."
            
        # Add formatted JSON to response
        formatted_json = json.dumps(chart_data, indent=2)
        full_response = f"{response_text}\n\n```json\n{formatted_json}\n```"
        
        new_state["chart_content"] = full_response
        new_state["chart_data"] = chart_data
        new_state["answer"] = full_response
        new_state["image_analysis"] = image_analysis
        
        if session_id:
            conversation_memory.add_assistant_message(
                session_id,
                full_response,
                source="visualization"
            )
        
        if chart_data:
            visualization_data = {  
                "chart_data": chart_data,
                "chart_type": chart_data.get("chartType"),
                "chart_title": chart_data.get("config", {}).get("title", "Chart")
            }
            
            # Add image analysis to visualization data if available
            if image_analysis:
                visualization_data["image_analysis"] = image_analysis
                
            log_thought(
                session_id=session_id,
                type="thought",
                category="visualization_data", 
                node="Visualization",
                content=response_text if response_text else "Visualization generated",
                visualization=visualization_data
            )
        
        # Clear retry tracking on success
        new_state["metadata"]["visualization_retry_count"] = 0
        new_state["metadata"]["visualization_error"] = ""
        new_state["route_to"] = END
        return new_state
        
    except Exception as e:
        logger.error(f"Error generating visualization (attempt {retry_count + 1}): {str(e)}")
        
        # Check if we should retry
        if retry_count < max_retries:
            # Increment retry count and store error for next attempt
            new_state["metadata"]["visualization_retry_count"] = retry_count + 1
            new_state["metadata"]["visualization_error"] = str(e)
            
            log_thought(
                session_id=session_id,
                type="thought",
                category="error",
                node="Visualization",
                content=f"Visualization attempt {retry_count + 1} failed: {str(e)}. Preparing to retry..."
            )
            
            # Return to same node for retry
            new_state["route_to"] = "visualize_data"
            return new_state
        else:
            # Max retries exceeded - graceful failure
            error_message = f"I apologize, but I encountered persistent issues generating the visualization after {max_retries + 1} attempts. The final error was: {str(e)}\n\nPlease try rephrasing your visualization request or provide more specific requirements for the chart you'd like to see."
            
            log_thought(
                session_id=session_id,
                type="thought",
                category="error",
                node="Visualization",
                content=f"Visualization failed after {max_retries + 1} attempts. Final error: {str(e)}. Gracefully ending workflow."
            )
            
            if session_id:
                conversation_memory.add_assistant_message(
                    session_id,
                    error_message,
                    source="visualization_error"
                )
            
            # Clear retry tracking and gracefully end
            new_state["metadata"]["visualization_retry_count"] = 0
            new_state["metadata"]["visualization_error"] = ""
            new_state["chart_content"] = error_message
            new_state["error"] = str(e)
            new_state["answer"] = error_message
            new_state["route_to"] = END
            return new_state
