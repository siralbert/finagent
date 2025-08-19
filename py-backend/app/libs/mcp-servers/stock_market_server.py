from typing import List, Union, Dict, Any, Optional
from mcp.server.fastmcp import FastMCP
import logging
import json
import time
import asyncio
import aiohttp
from datetime import datetime, timedelta
import argparse
import yfinance as yf

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("stock-market-server")

# Initialize FastMCP server
mcp = FastMCP("stock_market", log_level="INFO")

# Rate limiting implementation
RATE_LIMIT = {
    "per_minute": 20,  
    "per_day": 500
}

request_count = {
    "minute": 0,
    "day": 0,
    "last_minute_reset": time.time(),
    "last_day_reset": time.time()
}

def check_rate_limit():
    """Check and update rate limits for API calls"""
    now = time.time()
    
    if now - request_count["last_minute_reset"] > 60:
        request_count["minute"] = 0
        request_count["last_minute_reset"] = now
    
    if now - request_count["last_day_reset"] > 86400:
        request_count["day"] = 0
        request_count["last_day_reset"] = now
    
    if (request_count["minute"] >= RATE_LIMIT["per_minute"] or 
            request_count["day"] >= RATE_LIMIT["per_day"]):
        raise Exception('Rate limit exceeded. Please try again later.')
    
    request_count["minute"] += 1
    request_count["day"] += 1

# Helper functions for formatting output
def format_number(num):
    """Format a number with commas and 2 decimal places"""
    if num is None:
        return 'N/A'
    try:
        return f"{num:,.2f}"
    except (ValueError, TypeError):
        return 'N/A'

def format_percent(num):
    """Format a number as a percentage with 2 decimal places"""
    if num is None:
        return 'N/A'
    try:
        return f"{num*100:.2f}%"
    except (ValueError, TypeError):
        return 'N/A'

def format_stock_quote(quote):
    """Format stock quote data for display"""
    result = f"""
    Symbol: {quote['symbol']}
    Name: {quote['shortName'] or 'N/A'}
    Price: ${format_number(quote['regularMarketPrice'])}
    Change: ${format_number(quote['regularMarketChange'])} ({format_percent(quote['regularMarketChangePercent'] if quote['regularMarketChangePercent'] is not None else None)})
    Previous Close: ${format_number(quote['regularMarketPreviousClose'])}
    Open: ${format_number(quote['regularMarketOpen'])}
    Day Range: ${format_number(quote['regularMarketDayLow'])} - ${format_number(quote['regularMarketDayHigh'])}
    52 Week Range: ${format_number(quote['fiftyTwoWeekLow'])} - ${format_number(quote['fiftyTwoWeekHigh'])}
    Volume: {format_number(quote['regularMarketVolume'])}
    Avg. Volume: {format_number(quote['averageDailyVolume3Month'])}
    Market Cap: ${format_number(quote['marketCap'])}
    P/E Ratio: {format_number(quote['trailingPE'])}
    EPS: ${format_number(quote['epsTrailingTwelveMonths'])}
    Dividend Yield: {format_percent(quote['dividendYield'])}
    """.strip()
    
    return result

def format_market_data(indices):
    """Format market indices data for display"""
    result_parts = []
    
    for index in indices:
        change_percent = format_percent(index['regularMarketChangePercent'] if index['regularMarketChangePercent'] is not None else None)
        
        index_data = f"""
        {index['shortName'] or index['symbol']}
        Price: {format_number(index['regularMarketPrice'])}
        Change: {format_number(index['regularMarketChange'])} ({change_percent})
        Previous Close: {format_number(index['regularMarketPreviousClose'])}
        Day Range: {format_number(index['regularMarketDayLow'])} - {format_number(index['regularMarketDayHigh'])}
        """.strip()
        
        result_parts.append(index_data)
    
    return '\n\n'.join(result_parts)

# MCP tool definitions
@mcp.tool()
async def yahoo_stock_quote(symbol: str) -> str:
    """
    Get current stock quote information from Yahoo Finance.
    Returns detailed information about a stock including current price,
    day range, 52-week range, market cap, volume, P/E ratio, etc.
    
    Args:
        symbol: Stock ticker symbol (e.g., AAPL, MSFT, TSLA)
    """
    try:
        # Use yfinance library
        loop = asyncio.get_event_loop()
        ticker = await loop.run_in_executor(None, yf.Ticker, symbol)
        info = await loop.run_in_executor(None, lambda: ticker.info)
        
        if not info:
            return f"No data found for symbol: {symbol}"
            
        # Format the response
        quote_data = {
            "symbol": symbol,
            "shortName": info.get("shortName") or info.get("longName") or symbol,
            "regularMarketPrice": info.get("regularMarketPrice"),
            "regularMarketChange": info.get("regularMarketChange"),
            "regularMarketChangePercent": info.get("regularMarketChangePercent"),
            "regularMarketPreviousClose": info.get("regularMarketPreviousClose"),
            "regularMarketOpen": info.get("regularMarketOpen"),
            "regularMarketDayLow": info.get("regularMarketDayLow"),
            "regularMarketDayHigh": info.get("regularMarketDayHigh"),
            "fiftyTwoWeekLow": info.get("fiftyTwoWeekLow"),
            "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh"),
            "regularMarketVolume": info.get("regularMarketVolume"),
            "averageDailyVolume3Month": info.get("averageDailyVolume3Month"),
            "marketCap": info.get("marketCap"),
            "trailingPE": info.get("trailingPE"),
            "epsTrailingTwelveMonths": info.get("epsTrailingTwelveMonths"),
            "dividendYield": info.get("dividendYield")
        }
        
        return format_stock_quote(quote_data)
    except Exception as e:
        logger.error(f"Error in yahoo_stock_quote: {str(e)}")
        return f"Error retrieving stock quote: {str(e)}"

@mcp.tool()
async def yahoo_stock_history(symbol: str, period: str = "1mo", interval: str = "1d") -> str:
    """
    Get historical stock data from Yahoo Finance.
    Returns price and volume data for a specified time period.
    Useful for charting, trend analysis, and evaluating stock performance over time.
    
    Args:
        symbol: Stock ticker symbol (e.g., AAPL, MSFT, TSLA)
               or market index symbol (e.g., ^GSPC for S&P 500, ^DJI for Dow Jones, ^IXIC for NASDAQ)
        period: Time period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
        interval: Data interval (1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo)
    """
    try:
        check_rate_limit()
        
        # Validate period and interval
        valid_periods = ['1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'ytd', 'max']
        valid_intervals = ['1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h', '1d', '5d', '1wk', '1mo', '3mo']
        
        if period not in valid_periods:
            raise ValueError(f"Invalid period: {period}. Valid periods are: {', '.join(valid_periods)}")
        
        if interval not in valid_intervals:
            raise ValueError(f"Invalid interval: {interval}. Valid intervals are: {', '.join(valid_intervals)}")
        
        # Use yfinance library
        loop = asyncio.get_event_loop()
        ticker = await loop.run_in_executor(None, yf.Ticker, symbol)
        history = await loop.run_in_executor(None, lambda: ticker.history(period=period, interval=interval))
        
        if history.empty:
            return f"No historical data found for symbol: {symbol}"
        
        # Format the output
        result = f"Historical data for {symbol} ({period}, {interval} intervals)\n"
        result += f"Currency: {ticker.info.get('currency', 'USD')}\n\n"
        
        # Table header
        result += "Date       | Open     | High     | Low      | Close    | Volume\n"
        result += "-----------|----------|----------|----------|----------|-----------\n"
        
        # Sample data to avoid overwhelming response
        max_points = 10
        step = max(1, len(history) // max_points)
        
        # Format data rows
        for i in range(0, len(history), step):
            date = history.index[i].strftime('%Y-%m-%d')
            
            open_price = history['Open'].iloc[i] if 'Open' in history.columns else None
            high = history['High'].iloc[i] if 'High' in history.columns else None
            low = history['Low'].iloc[i] if 'Low' in history.columns else None
            close = history['Close'].iloc[i] if 'Close' in history.columns else None
            volume = history['Volume'].iloc[i] if 'Volume' in history.columns else None
            
            open_str = f"${open_price:.2f}" if open_price is not None else 'N/A'
            high_str = f"${high:.2f}" if high is not None else 'N/A'
            low_str = f"${low:.2f}" if low is not None else 'N/A'
            close_str = f"${close:.2f}" if close is not None else 'N/A'
            volume_str = f"{volume:,}" if volume is not None else 'N/A'
            
            result += f"{date.ljust(11)} | {open_str.ljust(8)} | {high_str.ljust(8)} | {low_str.ljust(8)} | {close_str.ljust(8)} | {volume_str}\n"
        
        # Add summary
        if not history.empty and 'Close' in history.columns:
            first_close = history['Close'].iloc[0]
            last_close = history['Close'].iloc[-1]
            
            change = last_close - first_close
            percent_change = (change / first_close) * 100 if first_close else 0
            
            result += f"\nPrice Change: ${change:.2f} ({percent_change:.2f}%)"
        
        return result
    except Exception as e:
        logger.error(f"Error in yahoo_stock_history: {str(e)}")
        return f"Error retrieving stock history: {str(e)}"

@mcp.tool()
async def yahoo_market_data(indices: List[str] = None) -> str:
    """
    Get current market data from Yahoo Finance.
    Returns information about major market indices (like S&P 500, NASDAQ, Dow Jones).
    Use this for broad market overview and current market sentiment.
    
    Args:
        indices: List of index symbols to fetch (e.g., ^GSPC for S&P 500, ^DJI for Dow Jones)
                Default: ["^GSPC", "^DJI", "^IXIC"] (S&P 500, Dow Jones, NASDAQ)
    """
    try:
        check_rate_limit()
        
        if indices is None:
            indices = ["^GSPC", "^DJI", "^IXIC"]  # Default indices: S&P 500, Dow Jones, NASDAQ
        
        loop = asyncio.get_event_loop()
        index_results = []
        
        for index_symbol in indices:
            try:
                ticker = await loop.run_in_executor(None, yf.Ticker, index_symbol)
                info = await loop.run_in_executor(None, lambda: ticker.info)
                
                if info:
                    index_results.append({
                        "symbol": index_symbol,
                        "shortName": info.get('shortName') or info.get('longName') or index_symbol,
                        "regularMarketPrice": info.get('regularMarketPrice'),
                        "regularMarketChange": info.get('regularMarketChange'),
                        "regularMarketChangePercent": info.get('regularMarketChangePercent'),
                        "regularMarketPreviousClose": info.get('regularMarketPreviousClose'),
                        "regularMarketDayHigh": info.get('regularMarketDayHigh'),
                        "regularMarketDayLow": info.get('regularMarketDayLow')
                    })
            except Exception as error:
                logger.error(f"Failed to fetch data for index: {index_symbol}. Error: {str(error)}")
        
        if index_results:
            return format_market_data(index_results)
        
        return "Unable to retrieve market data. Yahoo Finance data may be temporarily unavailable."
    except Exception as e:
        return f"Error retrieving market data: {str(e)}"

def main():
    """Main function to run the server"""
    parser = argparse.ArgumentParser(description='Run Yahoo Finance MCP server')
    parser.add_argument('--port', type=int, default=8083, help='Port to run the server on')
    
    args = parser.parse_args()
    
    mcp.settings.port = args.port
    logger.info(f"Starting Yahoo Finance server with Streamable HTTP transport on port {args.port}")
    mcp.run(transport='streamable-http')

if __name__ == "__main__":
    main()
