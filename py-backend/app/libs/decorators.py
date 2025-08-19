import logging
import functools
import asyncio
from typing import Dict, Callable, Any, Optional, Type, Union
from app.libs.types import GraphState
from app.libs.thought_stream import thought_handler

logger = logging.getLogger(__name__)


def with_thought_callback(category: str, node_name: Optional[str] = None):
    def decorator(func: Callable):
        func_node_name = node_name or func.__name__
        is_async = asyncio.iscoroutinefunction(func)
        
        if is_async:
            @functools.wraps(func)
            async def async_wrapper(state: GraphState) -> GraphState:
                logger.debug(f"Entering {func_node_name} node")
                
                session_id = state.get("session_id")
                
                _send_thought(
                    session_id=session_id,
                    type="process",
                    category=category,
                    node=func_node_name,
                    content=f"Processing in {func_node_name}"
                )
                
                try:
                    result_state = await func(state)
                    if "metadata" not in result_state:
                        result_state["metadata"] = {}
                    result_state["metadata"]["last_active_node"] = func_node_name
                    return result_state
                except Exception as e:
                    _send_thought(
                        session_id=session_id,
                        type="error",
                        category="error",
                        node=func_node_name,
                        content=f"Error in {func_node_name}: {str(e)}",
                        technical_details={"error": str(e)}
                    )
                    raise
            
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(state: GraphState) -> GraphState:
                logger.debug(f"Entering {func_node_name} node")
                
                session_id = state.get("session_id")
                
                _send_thought(
                    session_id=session_id,
                    type="process",
                    category=category,
                    node=func_node_name,
                    content=f"Processing in {func_node_name}"
                )
                
                try:
                    result_state = func(state)
                    if "metadata" not in result_state:
                        result_state["metadata"] = {}
                    result_state["metadata"]["last_active_node"] = func_node_name
                    return result_state
                except Exception as e:
                    _send_thought(
                        session_id=session_id,
                        type="error",
                        category="error",
                        node=func_node_name,
                        content=f"Error in {func_node_name}: {str(e)}",
                        technical_details={"error": str(e)}
                    )
                    raise
            
            return sync_wrapper
    
    return decorator


def _send_thought(session_id: Optional[str], type: str, category: str, node: str, 
                 content: Union[str, Dict[str, Any]], **kwargs) -> None:
    if not session_id:
        return
        
    thought_cb = thought_handler.get_callback(session_id)
    if thought_cb:
        thought = {
            "type": type,
            "category": category,
            "node": node,
            "content": content
        }
        thought.update(kwargs)
        thought_cb(thought)


def log_thought(session_id: Optional[str], type: str, category: str, node: str, 
               content: Union[str, Dict[str, Any]], **kwargs) -> None:
    _send_thought(session_id, type, category, node, content, **kwargs)