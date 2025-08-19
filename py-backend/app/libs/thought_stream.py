import asyncio
import json
import logging
import time
from queue import Queue
from threading import Event
from typing import Dict, Any, Callable, AsyncIterator

logger = logging.getLogger("thought_stream")

class ThoughtStore:
    def __init__(self):
        self.queues = {}
        self.events = {}
        
    def register_session(self, session_id: str) -> Queue:
        if session_id in self.queues:
            return self.queues[session_id]
        
        self.queues[session_id] = Queue()
        self.events[session_id] = Event()
        return self.queues[session_id]

    def unregister_session(self, session_id: str):
        logger.info(f"Unregistering session: {session_id}")
        
        if session_id in self.queues:
            del self.queues[session_id]
        if session_id in self.events:
            del self.events[session_id]
    
    def add_thought(self, session_id: str, thought: Dict[str, Any]):
        if session_id in self.queues:
            logger.debug(f"Adding thought to queue for session {session_id}")
            self.queues[session_id].put(thought)
            queue_size = self.queues[session_id].qsize()
        else:
            logger.warning(f"Attempted to add thought to non-existent session: {session_id}")
    
    def mark_complete(self, session_id: str):
        if session_id in self.events:
            logger.debug(f"Marking session complete: {session_id}")
            self.events[session_id].set()
        else:
            logger.warning(f"Attempted to mark non-existent session as complete: {session_id}")
    
    def is_complete(self, session_id: str) -> bool:
        result = session_id in self.events and self.events[session_id].is_set()
        return result


class ThoughtProcessHandler:
    def __init__(self):
        self.thought_store = ThoughtStore()
        self.callbacks = {}
    
    def thought_callback(self, session_id: str) -> Callable[[Dict[str, Any]], None]:
        """Creates a callback function that adds thoughts to the store for a specific session"""
        def _callback(thought: Dict[str, Any]) -> None:
            thought_type = thought.get('type', 'unknown')
            
            content_summary = ""
            content = thought.get('content', {})
            
            if isinstance(content, dict):
                if 'query' in content:
                    content_summary += f"query: {content['query'][:50]}... "
                if 'reasoning' in content:
                    content_summary += f"reasoning: {content['reasoning'][:50]}... "
                if 'function' in content:
                    content_summary += f"function: {content['function']} "
                if 'parameters' in content and isinstance(content['parameters'], list):
                    params = ", ".join([f"{p.get('name')}={p.get('value')}" for p in content['parameters'][:2]])
                    content_summary += f"params: {params} "
            else:
                content_summary = str(content)[:100] + "..." if len(str(content)) > 100 else str(content)
                
            logger.info(f"Received thought for session {session_id}: Type={thought_type}, Content={content_summary}")
            self.thought_store.add_thought(session_id, thought)
        
        logger.debug(f"Created thought callback for session {session_id}")
        self.callbacks[session_id] = _callback
        return _callback
    
    def get_callback(self, session_id: str) -> Callable[[Dict[str, Any]], None]:
        if session_id in self.callbacks:
            return self.callbacks[session_id]
        
        return self.thought_callback(session_id)

    def register_session(self, session_id: str) -> Queue:
        """Register a new session for thought streaming"""
        logger.info(f"Registering thought stream session: {session_id}")
        return self.thought_store.register_session(session_id)
    
    def mark_session_complete(self, session_id: str) -> None:
        """Mark a session as completed"""
        logger.info(f"Marking session complete: {session_id}")
        self.thought_store.mark_complete(session_id)
        
        if session_id in self.callbacks:
            del self.callbacks[session_id]
    
    async def stream_generator(self, session_id: str) -> AsyncIterator[str]:
        logger.info(f"Setting up SSE stream generator for session: {session_id}")
        
        if session_id not in self.thought_store.queues:
            logger.info(f"Creating pre-registered session for SSE: {session_id}")
            self.thought_store.register_session(session_id)
            self.thought_store.pending_sessions = getattr(self.thought_store, 'pending_sessions', set())
            self.thought_store.pending_sessions.add(session_id)
        
        queue = self.thought_store.queues[session_id]
        def format_sse(data: dict) -> str:
            message = f"data: {json.dumps(data)}\n\n"
            return message
        
        connection_msg = {"type": "connected", "message": "Thought process stream connected"}
        yield format_sse(connection_msg)
        await asyncio.sleep(0.1)
        
        cached_thoughts = []
        while not queue.empty():
            try:
                cached_thoughts.append(queue.get_nowait())
            except:
                break
        
        for idx, thought in enumerate(cached_thoughts):
            if "id" not in thought:
                thought["id"] = f"{session_id}-cached-{idx}"
            yield format_sse(thought)
            
            # Tool-related cached thoughts get immediate streaming
            thought_category = thought.get('category', '')
            if thought_category == 'tool' or 'tool' in thought.get('node', '').lower():
                await asyncio.sleep(0.01)  # Immediate for tool events
            else:
                await asyncio.sleep(0.1)   # Delayed for other events
        
        thought_count = len(cached_thoughts)
        ping_count = 0
        
        while not self.thought_store.is_complete(session_id) or not queue.empty():
            try:
                if not queue.empty():
                    thought = queue.get_nowait()
                    thought_count += 1
                    
                    if "id" not in thought:
                        thought["id"] = f"{session_id}-thought-{thought_count}"
                        
                    logger.info(f"Streaming thought #{thought_count} for session {session_id}: {thought.get('type', 'unknown')}")
                    yield format_sse(thought)
                    
                    # Tool-related thoughts get immediate streaming, others get delay
                    thought_category = thought.get('category', '')
                    if thought_category == 'tool' or 'tool' in thought.get('node', '').lower():
                        await asyncio.sleep(0.01)  # Immediate for tool events
                    else:
                        await asyncio.sleep(0.1)   # Delayed for other events
                else:
                    ping_count += 1
                    if ping_count >= 10:  
                        ping_count = 0
                        yield format_sse({"type": "ping", "timestamp": f"{time.time()}"})
                    
                    await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Error in thought stream for session {session_id}: {e}")
                yield format_sse({"type": "error", "message": str(e)})
                await asyncio.sleep(0.5)
        
        complete_msg = {"type": "complete", "message": "Thought process complete"}
        yield format_sse(complete_msg)
        
        self.thought_store.unregister_session(session_id)

# Create a singleton instance
thought_handler = ThoughtProcessHandler()
