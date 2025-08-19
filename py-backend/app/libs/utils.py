import boto3
import base64
import logging
from typing import Dict, List, Any, Tuple
from botocore.config import Config

logger = logging.getLogger(__name__)

bedrock_clients = {}
bedrock_agent_clients = {}
bedrock_session_savers = {}
default_region = "us-west-2"

def extract_message_content(message: Dict[str, Any]):
    content = message.get('content', '')
    text_content = ''
    file_data = None
    
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                if "text" in item:
                    text_content += item["text"]
                elif "image" in item or "file" in item:
                    file_data = item
    else:
        text_content = str(content)
        
    return text_content, file_data

def create_bedrock_client(region):
    config = Config(
        region_name=region,
        max_pool_connections=10,
        connect_timeout=5,
        read_timeout=30,
        retries={"max_attempts": 2}
    )
    return boto3.client('bedrock-runtime', region_name=region, config=config)

def create_bedrock_agent_client(region):
    config = Config(
        region_name=region,
        max_pool_connections=10,
        connect_timeout=5,
        read_timeout=30,
        retries={"max_attempts": 2}
    )
    return boto3.client('bedrock-agent-runtime', region_name=region, config=config)

def get_or_create_clients(region=None):
    """Get or create Bedrock clients for the specified region"""
    if region is None:
        region = default_region
        
    if region not in bedrock_clients:
        bedrock_clients[region] = create_bedrock_client(region=region)
        bedrock_agent_clients[region] = create_bedrock_agent_client(region=region)
    
    return {
        "bedrock_client": bedrock_clients[region],
        "bedrock_agent_client": bedrock_agent_clients[region],
    }

def prepare_messages_with_binary_data(messages):
    processed_messages = []
    
    for msg in messages:
        if not msg.get('content'):
            continue
            
        processed_content = []
        
        for content_item in msg.get('content', []):
            if isinstance(content_item, dict):
                if 'text' in content_item:
                    processed_content.append({'text': content_item['text']})
                
                elif 'image' in content_item:
                    image_item = {'image': {}}
                    image_item['image']['format'] = content_item['image'].get('format', 'png')
                    
                    if 'source' in content_item['image']:
                        source = content_item['image']['source']
                        image_item['image']['source'] = {}
                        
                        if 'bytes' in source:
                            bytes_data = source['bytes']
                            
                            if isinstance(bytes_data, dict):
                                if 'source' in bytes_data and 'bytes' in bytes_data['source']:
                                    inner_bytes = bytes_data['source']['bytes']
                                    if isinstance(inner_bytes, str):
                                        try:
                                            image_item['image']['source']['bytes'] = base64.b64decode(inner_bytes)
                                        except:
                                            image_item['image']['source']['bytes'] = b'dummy_data'
                                    else:
                                        image_item['image']['source']['bytes'] = inner_bytes or b'dummy_data'
                                else:
                                    image_item['image']['source']['bytes'] = b'dummy_data'
                            
                            elif isinstance(bytes_data, str):
                                try:
                                    image_item['image']['source']['bytes'] = base64.b64decode(bytes_data)
                                except:
                                    image_item['image']['source']['bytes'] = bytes_data.encode() if bytes_data else b'dummy_data'
                            
                            elif isinstance(bytes_data, bytes):
                                image_item['image']['source']['bytes'] = bytes_data
                            
                            else:
                                image_item['image']['source']['bytes'] = b'dummy_data'
                    
                    if 'source' in image_item['image'] and 'bytes' in image_item['image']['source']:
                        processed_content.append(image_item)
            
            elif isinstance(content_item, str):
                processed_content.append({'text': content_item})
        
        if processed_content:
            processed_messages.append({
                'role': msg['role'],
                'content': processed_content
            })
    
    if not processed_messages:
        processed_messages.append({
            'role': 'user',
            'content': [{'text': 'Can you help me visualize this data?'}]
        })
    elif processed_messages[0]['role'] != 'user':
        processed_messages.insert(0, {
            'role': 'user',
            'content': [{'text': 'Can you help me visualize this data?'}]
        })
    
    return processed_messages