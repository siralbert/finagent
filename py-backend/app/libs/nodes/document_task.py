import logging
import asyncio
from typing import Dict, Any, Optional
from app.libs.types import GraphState
from app.libs.utils import create_bedrock_client, prepare_messages_with_binary_data
from app.libs.decorators import with_thought_callback, log_thought
from app.libs.conversation_memory import conversation_memory
from app.libs.mcp_client_factory import get_mcp_client
from langgraph.graph import END

logger = logging.getLogger(__name__)

@with_thought_callback(category="document", node_name="Document Task")
async def handle_document_generation(state: GraphState) -> GraphState:
    """
    Handle document generation tasks using Word Generator MCP server
    """
    logger.info("Document task node: Processing document generation request...")
    
    new_state = state.copy()
    query = new_state.get("extracted_text", "")
    session_id = new_state.get("session_id")
    
    if "metadata" not in new_state:
        new_state["metadata"] = {}
    new_state["metadata"]["last_active_node"] = "document_task"
    
    try:
        # Get MCP client for word generator
        word_client = get_mcp_client("word")
        if not word_client:
            error_msg = "Word Generator service is not available. Please ensure the Word Generator MCP server is running."
            logger.error(error_msg)
            new_state["answer"] = error_msg
            return new_state
        
        log_thought(
            session_id=session_id,
            type="process",
            category="document_generation",
            node="Document Task",
            content="Analyzing document generation request"
        )
        
        # Analyze the request to determine document type and parameters
        analysis_result = await analyze_document_request(query, session_id)
        
        if analysis_result.get("error"):
            new_state["answer"] = analysis_result["error"]
            return new_state
        
        doc_type = analysis_result.get("document_type", "general")
        filename = analysis_result.get("filename", "document.docx")
        title = analysis_result.get("title")
        content = analysis_result.get("content", query)
        
        log_thought(
            session_id=session_id,
            type="thought",
            category="document_generation",
            node="Document Task",
            content=f"Generating {doc_type} document: {filename}"
        )
        
        # Generate document based on type
        if doc_type == "financial_report":
            result = await generate_financial_report(word_client, filename, content, analysis_result)
        elif doc_type == "chart_document":
            result = await generate_chart_document(word_client, filename, content, analysis_result)
        else:
            result = await generate_general_document(word_client, filename, content, title)
        
        new_state["answer"] = result
        
        # Add to conversation memory
        if session_id:
            conversation_memory.add_assistant_message(
                session_id,
                result,
                source="document_task"
            )
        
        log_thought(
            session_id=session_id,
            type="thought",
            category="document_generation",
            node="Document Task",
            content="Document generation completed"
        )
        
        return new_state
        
    except Exception as e:
        error_msg = f"Error in document generation: {str(e)}"
        logger.error(error_msg)
        new_state["answer"] = error_msg
        return new_state

async def analyze_document_request(query: str, session_id: str) -> Dict[str, Any]:
    """
    Analyze the user's request to determine document type and parameters
    """
    try:
        # Create Bedrock client for analysis
        bedrock_client = create_bedrock_client()
        
        analysis_prompt = f"""
        Analyze this document generation request and extract the following information:
        
        Request: "{query}"
        
        Determine:
        1. Document type: "financial_report", "chart_document", or "general"
        2. Suggested filename (without spaces, with .docx extension)
        3. Document title
        4. Main content or requirements
        
        Respond in JSON format:
        {{
            "document_type": "type_here",
            "filename": "suggested_filename.docx",
            "title": "Document Title",
            "content": "Main content or description of what should be included"
        }}
        """
        
        messages = [
            {
                "role": "user",
                "content": [{"text": analysis_prompt}]
            }
        ]
        
        response = await bedrock_client.invoke_model_async(
            modelId="anthropic.claude-3-5-sonnet-20241022-v2:0",
            contentType="application/json",
            accept="application/json",
            body={
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1000,
                "messages": messages,
                "system": "You are a document analysis assistant. Always respond with valid JSON only."
            }
        )
        
        # Extract response text
        response_text = ""
        if "output" in response and "message" in response["output"]:
            output_message = response["output"]["message"]
            if "content" in output_message:
                for content_item in output_message["content"]:
                    if "text" in content_item:
                        response_text += content_item["text"]
        
        # Parse JSON response
        import json
        import re
        json_pattern = r"```json\s*([\s\S]*?)\s*```|(\{[\s\S]*\})"
        json_matches = re.findall(json_pattern, response_text)
        
        if json_matches:
            json_str = json_matches[0][0] or json_matches[0][1]
            analysis_result = json.loads(json_str)
            return analysis_result
        else:
            # Try to parse the entire response as JSON
            return json.loads(response_text)
            
    except Exception as e:
        logger.error(f"Error analyzing document request: {str(e)}")
        return {
            "document_type": "general",
            "filename": "document.docx",
            "title": "Generated Document",
            "content": query
        }

async def generate_financial_report(word_client, filename: str, content: str, analysis: Dict[str, Any]) -> str:
    """Generate a financial report document"""
    try:
        # Prepare financial report data structure
        report_data = {
            "summary": content,
            "highlights": [
                "Document generated from financial analysis",
                "Based on user request and available data"
            ],
            "metrics": {
                "Generated": "Automatically",
                "Type": "Financial Report",
                "Format": "Word Document"
            }
        }
        
        result = await word_client.call_tool(
            "format_financial_report",
            {
                "filename": filename,
                "data": report_data,
                "title": analysis.get("title", "Financial Report")
            }
        )
        
        return f"Financial report generated successfully.\n\n{result}"
        
    except Exception as e:
        logger.error(f"Error generating financial report: {str(e)}")
        return f"Error generating financial report: {str(e)}"

async def generate_chart_document(word_client, filename: str, content: str, analysis: Dict[str, Any]) -> str:
    """Generate a document with charts"""
    try:
        result = await word_client.call_tool(
            "generate_document_with_charts",
            {
                "filename": filename,
                "content": content,
                "title": analysis.get("title", "Chart Document")
            }
        )
        
        return f"Chart document generated successfully.\n\n{result}"
        
    except Exception as e:
        logger.error(f"Error generating chart document: {str(e)}")
        return f"Error generating chart document: {str(e)}"

async def generate_general_document(word_client, filename: str, content: str, title: Optional[str] = None) -> str:
    """Generate a general document"""
    try:
        result = await word_client.call_tool(
            "generate_document",
            {
                "filename": filename,
                "content": content,
                "title": title or "Generated Document"
            }
        )
        
        return f"Document generated successfully.\n\n{result}"
        
    except Exception as e:
        logger.error(f"Error generating general document: {str(e)}")
        return f"Error generating general document: {str(e)}"