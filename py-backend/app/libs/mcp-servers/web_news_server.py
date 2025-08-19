from typing import List, Dict, Any, Optional
from mcp.server.fastmcp import FastMCP
import logging
import asyncio
import yfinance as yf
from pydantic import Field
from datetime import datetime
import httpx
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
import argparse
import sys
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("financial-news-server")

mcp = FastMCP("financial-news", log_level="INFO")

RATE_LIMIT = {"per_minute": 15, "per_day": 300}
request_count = {
    "minute": 0, "day": 0,
    "last_minute_reset": time.time(),
    "last_day_reset": time.time()
}

def check_rate_limit():
    now = time.time()
    
    if now - request_count["last_minute_reset"] > 60:
        request_count["minute"] = 0
        request_count["last_minute_reset"] = now
    
    if now - request_count["last_day_reset"] > 86400:
        request_count["day"] = 0
        request_count["last_day_reset"] = now
    
    if (request_count["minute"] >= RATE_LIMIT["per_minute"] or request_count["day"] >= RATE_LIMIT["per_day"]):
        raise Exception('Rate limit exceeded. Please try again later.')
    
    request_count["minute"] += 1
    request_count["day"] += 1

class APIError(Exception):
    pass

class DuckDuckGoSearcher:
    def __init__(self):
        self.ddgs = DDGS()

    async def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_search, query, max_results)
    
    def _sync_search(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        try:
            results = []
            for r in self.ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", "No title"),
                    "content": r.get("body", "No content"),
                    "url": r.get("href", ""),
                    "source": "DuckDuckGo"
                })
            return results
        except Exception as e:
            logger.error(f"DuckDuckGo search error: {e}")
            raise APIError(f"Error performing web search: {str(e)}")

web_searcher = DuckDuckGoSearcher()

def parse_news_item(item):
    try:
        content = item.get('content', item)
        
        provider_name = "Unknown"
        if 'provider' in content and isinstance(content['provider'], dict):
            provider_name = content['provider'].get('displayName', provider_name)
        
        pub_date = datetime.now().isoformat()
        if 'pubDate' in content:
            pub_date = content['pubDate']
        elif 'providerPublishTime' in content and content['providerPublishTime']:
            pub_date = datetime.fromtimestamp(content['providerPublishTime']).isoformat()
        
        link = ""
        if 'clickThroughUrl' in content and isinstance(content['clickThroughUrl'], dict):
            link = content['clickThroughUrl'].get('url', "")
        elif 'link' in content:
            link = content['link']
        elif 'url' in content:
            link = content['url']
        
        summary = ""
        for field in ['summary', 'description', 'shortDescription', 'longDescription', 'snippetText']:
            if field in content and content[field]:
                summary = content[field]
                break
        
        return {
            "title": content.get("title", "No title available"),
            "publisher": provider_name,
            "link": link,
            "published_date": pub_date,
            "summary": summary
        }
    except Exception as e:
        logger.error(f"Error parsing news item: {str(e)}")
        return None

@mcp.tool()
async def financial_news(
    symbol: str = Field(description="Stock ticker symbol (e.g., AAPL, MSFT, TSLA)"),
    count: int = Field(5, description="Number of news articles to return (1-20)")
) -> str:
    """Get the latest financial news for a specific stock ticker symbol."""
    try:
        check_rate_limit()
        
        if not symbol or len(symbol.strip()) == 0:
            return "Please provide a valid stock ticker symbol."
        
        symbol = symbol.strip().upper()
        count = min(max(count, 1), 20)
        
        logger.info(f"Getting latest news for ticker: {symbol}, count: {count}")
        
        loop = asyncio.get_event_loop()
        ticker = await loop.run_in_executor(None, yf.Ticker, symbol)
        news_data = await loop.run_in_executor(None, lambda: ticker.news)
        
        if not news_data:
            logger.info(f"No news found for ticker {symbol}")
            return f"No recent news found for {symbol}."

        logger.info(f"Found {len(news_data)} news articles for {symbol}")
            
        formatted_news = []
        news_count = min(count, len(news_data))
        
        for item in news_data[:news_count]: 
            parsed_item = parse_news_item(item)
            if parsed_item:
                formatted_news.append(parsed_item)
        
        if not formatted_news:
            return f"No news articles could be processed for {symbol}."
            
        result = f"Latest news for {symbol} ({len(formatted_news)} articles):\n\n"
        for i, item in enumerate(formatted_news, 1):
            result += f"{i}. {item['title']}\n"
            result += f"   Publisher: {item['publisher']}\n"
            result += f"   Date: {item['published_date']}\n"
            if item['summary']:
                result += f"   Summary: {item['summary']}\n"
            if item['link']:
                result += f"   Link: {item['link']}\n"
            result += "\n"
                
        return result
            
    except Exception as e:
        logger.error(f"Error in financial_news: {str(e)}")
        return f"Error retrieving financial news: {str(e)}"

@mcp.tool()
async def web_search(
    query: str = Field(description="Search query for finding information"),
    max_results: int = Field(5, description="Maximum number of results to return")
) -> str:
    """Search the web for information on a topic."""
    logger.info(f"web_search called with query: {query}, max_results: {max_results}")
    try:
        results = await web_searcher.search(query, max_results)
        
        if not results:
            return "No search results found for your query."
        
        formatted_output = f"Search results for: {query}\n\n"
        
        for i, result in enumerate(results, 1):
            formatted_output += f"{i}. {result.get('title', 'No title')}\n"
            if result.get('url'):
                formatted_output += f"   URL: {result.get('url')}\n"
            if result.get('content'):
                content = result.get('content')
                formatted_output += f"   Summary: {content}\n"
            formatted_output += "\n"
        
        return formatted_output
        
    except Exception as e:
        logger.error(f"Error in web_search: {e}")
        return f"Error performing web search: {str(e)}"

def main():
    parser = argparse.ArgumentParser(description='Run Financial News MCP server')
    parser.add_argument('--port', type=int, default=8085, help='Port to run the server on')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    
    args = parser.parse_args()
    
    mcp.settings.port = args.port
    logger.info(f"Starting Financial News server with Streamable HTTP transport on port {args.port}")
    mcp.run(transport='streamable-http')

if __name__ == "__main__":
    main()