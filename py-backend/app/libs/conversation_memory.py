import logging
import json
import uuid
import base64
from typing import Dict, List, Any, Optional, Union
from datetime import datetime

logger = logging.getLogger(__name__)

class ConversationMemoryManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConversationMemoryManager, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize the conversation memory manager."""
        self.conversations = {} 
        self.files = {} 
        self.active_sessions = set()  
        self.session_expiry_seconds = 3600
        self.max_messages_per_conversation = 50
        self.sliding_window_size = 30  # Keep only the most recent 30 messages
        logger.info("ConversationMemoryManager initialized")
    
    def _apply_sliding_window(self, session_id: str) -> None:
        """Apply sliding window to keep only the most recent messages."""
        if session_id not in self.conversations:
            return
            
        messages = self.conversations[session_id]["messages"]
        if len(messages) <= self.sliding_window_size:
            return
            
        # Separate system messages from other messages
        system_messages = []
        other_messages = []
        
        for msg in messages:
            if msg.get('role') == 'system':
                system_messages.append(msg)
            else:
                other_messages.append(msg)
        
        # Keep all system messages + most recent user/assistant messages
        if len(other_messages) > self.sliding_window_size:
            # Keep the most recent messages within the window
            recent_messages = other_messages[-self.sliding_window_size:]
            self.conversations[session_id]["messages"] = system_messages + recent_messages
            
            removed_count = len(other_messages) - self.sliding_window_size
            logger.info(f"Applied sliding window to session {session_id}: removed {removed_count} old messages, kept {len(recent_messages)} recent + {len(system_messages)} system messages")
    
    def ensure_session_exists(self, session_id: str) -> bool:
        if session_id in self.conversations:
            return True
            
        self.conversations[session_id] = {
            "messages": [],
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
                "message_count": 0,
                "turn_count": 0
            }
        }
        
        logger.info(f"Initialized conversation memory for session: {session_id}")
        return True
    
    def add_user_message(self, session_id: str, content: str, file_data: Optional[Dict[str, Any]] = None) -> bool:
        if not self._validate_session(session_id):
            return False
                
        message_content = []
        if content:
            message_content.append({"text": content})
        
        if file_data and isinstance(file_data, dict) and "image" in file_data:
            image_id = f"image_{str(uuid.uuid4())}.png"  
            
            image_bytes = file_data["image"]
            if isinstance(image_bytes, str):
                try:
                    image_bytes = base64.b64decode(image_bytes)
                except:
                    pass
            
            message_content.append({
                "image": {
                    "format": "png",
                    "source": {
                        "bytes": image_bytes
                    },
                    "id": image_id 
                }
            })
            
            if session_id not in self.files:
                self.files[session_id] = []
            
            self.files[session_id].append({
                "name": image_id,
                "source": {
                    "byteContent": {
                        "data": image_bytes,
                        "mediaType": "image/png"
                    },
                    "sourceType": "BYTE_CONTENT"
                },
                "useCase": "CHAT"
            })
        
        message = {
            "role": "user",
            "content": message_content,
            "timestamp": datetime.now().isoformat()
        }
        
        self.conversations[session_id]["messages"].append(message)
        self._update_session_metadata(session_id, increment_turn=True)
        
        # Apply sliding window after adding message
        self._apply_sliding_window(session_id)
        
        return True

    
    def add_assistant_message(self, session_id: str, content: str, source: str = "direct_response") -> bool:
        if not self._validate_session(session_id):
            return False
            
        message = {
            "role": "assistant",
            "content": [{"text": content}],
            "timestamp": datetime.now().isoformat(),
            "metadata": {"source": source}
        }
        
        self.conversations[session_id]["messages"].append(message)
        self._update_session_metadata(session_id, increment_turn=True)
        
        # Apply sliding window after adding message
        self._apply_sliding_window(session_id)
        
        logger.debug(f"Added assistant message from {source} to session {session_id}: {content[:50]}...")
        return True
    

    def get_bedrock_inline_session_state(self, session_id: str) -> Dict[str, Any]:
        """Get session state formatted for Amazon Bedrock InlineAgent"""
        if not self._validate_session(session_id):
            return {"conversationHistory": {"messages": []}}
        
        all_messages = self.conversations[session_id]["messages"]

        processed_messages = []
        current_role = None
        
        for i, message in enumerate(all_messages):
            if i == len(all_messages) - 1 and message.get("role") == "user":
                break
                
            if "content" in message and isinstance(message["content"], list):
                combined_text = ""
                for content_block in message["content"]:
                    if isinstance(content_block, dict) and "text" in content_block:
                        combined_text += (content_block["text"] + " ")
                
                role = message.get("role", "user")
                
                if role == current_role:
                    if processed_messages:
                        last_text = processed_messages[-1]["content"][0]["text"]
                        processed_messages[-1]["content"][0]["text"] = f"{last_text.strip()}\n\n{combined_text.strip()}"
                else:
                    processed_messages.append({
                        "role": role,
                        "content": [{"text": combined_text.strip()}]
                    })
                    current_role = role
        
        if processed_messages and processed_messages[-1]["role"] == "user":
            processed_messages = processed_messages[:-1]
        
        return {
            "conversationHistory": {
                "messages": processed_messages
            }
        }


    def add_tool_usage_message(self, session_id: str, tool_name: str, parameters: Dict[str, Any]) -> bool:
        if not self._validate_session(session_id):
            return False
            
        # Format parameters for readability
        params_str = ", ".join([f"{k}={json.dumps(v)}" for k, v in parameters.items()])
        tool_message = f"Using tool: {tool_name}({params_str})"
        
        message = {
            "role": "assistant",
            "content": [{"text": tool_message}],
            "timestamp": datetime.now().isoformat(),
            "metadata": {"type": "tool_usage", "tool": tool_name}
        }
        
        self.conversations[session_id]["messages"].append(message)
        self._update_session_metadata(session_id)
        logger.debug(f"Added tool usage message to session {session_id}: {tool_name}")
        return True
    
    def add_tool_result_message(self, session_id: str, tool_name: str, result: Union[str, Dict, List]) -> bool:
        if not self._validate_session(session_id):
            return False
            
        # Format the result as a string
        if not isinstance(result, str):
            result_str = json.dumps(result, ensure_ascii=False)
        else:
            result_str = result
            
        tool_result_message = f"[{tool_name} result: {result_str}]"
        
        message = {
            "role": "user",
            "content": [{"text": tool_result_message}],
            "timestamp": datetime.now().isoformat(),
            "metadata": {"type": "tool_result", "tool": tool_name}
        }
        
        self.conversations[session_id]["messages"].append(message)
        self._update_session_metadata(session_id)
        logger.debug(f"Added tool result message to session {session_id} from {tool_name}")
        return True
    
    def get_conversation_history(self, session_id: str, max_messages: Optional[int] = None) -> Dict[str, List[Dict[str, Any]]]:
        if not self._validate_session(session_id):
            return {"messages": []}
        
        messages = self.conversations[session_id]["messages"]
        
        # Apply message limit if specified
        if max_messages and len(messages) > max_messages:
            messages = messages[-max_messages:]
            
        # Return in the format expected by Bedrock
        history = {"messages": []}
        
        for msg in messages:
            # Strip internal metadata before sending to Bedrock
            cleaned_msg = {
                "role": msg["role"],
                "content": msg["content"]
            }
            history["messages"].append(cleaned_msg)
            
        return history

    def get_raw_conversation(self, session_id: str) -> Dict[str, Any]:
        if not self._validate_session(session_id):
            return {"messages": [], "metadata": {}}
            
        return self.conversations[session_id]
    
    def clear_conversation(self, session_id: str) -> bool:
        if not self._validate_session(session_id):
            return False
            
        metadata = self.conversations[session_id]["metadata"].copy()
        metadata["last_updated"] = datetime.now().isoformat()
        metadata["message_count"] = 0
        metadata["turn_count"] = 0
        
        self.conversations[session_id] = {
            "messages": [],
            "metadata": metadata
        }
        
        logger.info(f"Cleared conversation for session {session_id}")
        return True
    
    def delete_session(self, session_id: str) -> bool:
        if session_id not in self.conversations:
            logger.warning(f"Session {session_id} not found for deletion")
            return False
            
        del self.conversations[session_id]
        
        if session_id in self.active_sessions:
            self.active_sessions.remove(session_id)
            
        logger.info(f"Deleted session {session_id}")
        return True
    
    def trim_conversation(self, session_id: str, max_messages: Optional[int] = None) -> bool:
        if not self._validate_session(session_id):
            return False
            
        if max_messages is None:
            max_messages = self.max_messages_per_conversation
            
        messages = self.conversations[session_id]["messages"]
        
        if len(messages) > max_messages:
            # Keep only the most recent messages
            self.conversations[session_id]["messages"] = messages[-max_messages:]
            self._update_session_metadata(session_id)
            logger.info(f"Trimmed session {session_id} to {max_messages} messages")
            
        return True
    
    def set_max_messages(self, max_messages: int) -> None:
        self.max_messages_per_conversation = max_messages
        logger.info(f"Set default max messages per conversation to {max_messages}")
    
    def cleanup_expired_sessions(self, max_age_seconds: Optional[int] = None) -> int:
        if max_age_seconds is None:
            max_age_seconds = self.session_expiry_seconds
            
        now = datetime.now()
        sessions_to_delete = []
        
        for session_id, conversation in self.conversations.items():
            last_updated_str = conversation["metadata"].get("last_updated")
            if not last_updated_str:
                continue
                
            try:
                last_updated = datetime.fromisoformat(last_updated_str)
                age_seconds = (now - last_updated).total_seconds()
                
                if age_seconds > max_age_seconds:
                    sessions_to_delete.append(session_id)
            except ValueError:
                logger.error(f"Invalid timestamp format in session {session_id}: {last_updated_str}")
                
        for session_id in sessions_to_delete:
            self.delete_session(session_id)
            
        if sessions_to_delete:
            logger.info(f"Cleaned up {len(sessions_to_delete)} expired sessions")
            
        return len(sessions_to_delete)

    def get_session_stats(self) -> Dict[str, Any]:
        stats = {
            "total_sessions": len(self.conversations),
            "active_sessions": len(self.active_sessions),
            "total_messages": sum(conv["metadata"].get("message_count", 0) for conv in self.conversations.values()),
            "average_messages_per_session": 0
        }
        
        if stats["total_sessions"] > 0:
            stats["average_messages_per_session"] = stats["total_messages"] / stats["total_sessions"]
            
        return stats
    
    def _validate_session(self, session_id: str) -> bool:
        if session_id not in self.conversations:
            logger.warning(f"Session {session_id} not found")
            return False
            
        return True
    
    def _update_session_metadata(self, session_id: str, increment_turn: bool = False) -> None:
        if session_id in self.conversations:
            metadata = self.conversations[session_id]["metadata"]
            metadata["last_updated"] = datetime.now().isoformat()
            metadata["message_count"] = len(self.conversations[session_id]["messages"])
            
            if increment_turn:
                metadata["turn_count"] = metadata.get("turn_count", 0) + 1

# Create singleton instance
conversation_memory = ConversationMemoryManager()
