from typing import List, Dict, Any, Optional
from mcp.server.fastmcp import FastMCP
import logging
import asyncio
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import time
import argparse

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("financial-analysis-server")

# Initialize FastMCP server
mcp = FastMCP("financial-analysis", log_level="INFO")

# Rate limiting implementation
RATE_LIMIT = {
    "per_minute": 10,
    "per_day": 300
}

request_count = {
    "minute": 0,
    "day": 0,
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
    
    if (request_count["minute"] >= RATE_LIMIT["per_minute"] or 
            request_count["day"] >= RATE_LIMIT["per_day"]):
        raise Exception('Rate limit exceeded. Please try again later.')
    
    request_count["minute"] += 1
    request_count["day"] += 1

class APIError(Exception):
    pass

# Helper functions for analysis interpretation
def interpret_rsi(rsi: float) -> str:
    if rsi >= 70: return "Overbought"
    elif rsi <= 30: return "Oversold"
    else: return "Neutral"

def interpret_macd(macd: float, signal: float) -> str:
    if macd > signal: return "Bullish"
    elif macd < signal: return "Bearish"
    else: return "Neutral"

def interpret_ma_trend(ma_distances: dict) -> str:
    if ma_distances["from_200sma"] > 0 and ma_distances["from_50sma"] > 0: return "Uptrend"
    elif ma_distances["from_200sma"] < 0 and ma_distances["from_50sma"] < 0: return "Downtrend"
    else: return "Mixed"

def interpret_relative_strength(stock_change: float, sp500_change: float) -> str:
    if stock_change > sp500_change: return "Outperforming market"
    elif stock_change < sp500_change: return "Underperforming market"
    else: return "Market performer"

async def fetch_fundamental_analysis(equity):
    check_rate_limit()
    
    try:
        ticker = yf.Ticker(equity)
        info = ticker.info
        if not info:
            raise ValueError(f"No fundamental data available for {equity}")
        
        return {
            "company_info": {
                "longName": info.get("longName"),
                "shortName": info.get("shortName"),
                "industry": info.get("industry"),
                "sector": info.get("sector"),
                "country": info.get("country"),
                "website": info.get("website"),
                "fullTimeEmployees": info.get("fullTimeEmployees"),
                "longBusinessSummary": info.get("longBusinessSummary")
            },
            "valuation_metrics": {
                "trailingPE": info.get("trailingPE"),
                "forwardPE": info.get("forwardPE"),
                "priceToBook": info.get("priceToBook"),
                "priceToSalesTrailing12Months": info.get("priceToSalesTrailing12Months"),
                "enterpriseValue": info.get("enterpriseValue"),
                "enterpriseToEbitda": info.get("enterpriseToEbitda"),
                "enterpriseToRevenue": info.get("enterpriseToRevenue"),
                "bookValue": info.get("bookValue")
            },
            "earnings_and_revenue": {
                "totalRevenue": info.get("totalRevenue"),
                "revenueGrowth": info.get("revenueGrowth"),
                "revenuePerShare": info.get("revenuePerShare"),
                "ebitda": info.get("ebitda"),
                "ebitdaMargins": info.get("ebitdaMargins"),
                "netIncomeToCommon": info.get("netIncomeToCommon"),
                "earningsGrowth": info.get("earningsGrowth"),
                "earningsQuarterlyGrowth": info.get("earningsQuarterlyGrowth"),
                "forwardEps": info.get("forwardEps"),
                "trailingEps": info.get("trailingEps")
            },
            "margins_and_returns": {
                "profitMargins": info.get("profitMargins"),
                "operatingMargins": info.get("operatingMargins"),
                "grossMargins": info.get("grossMargins"),
                "returnOnEquity": info.get("returnOnEquity"),
                "returnOnAssets": info.get("returnOnAssets")
            },
            "dividends": {
                "dividendYield": info.get("dividendYield"),
                "dividendRate": info.get("dividendRate"),
                "payoutRatio": info.get("payoutRatio"),
                "fiveYearAvgDividendYield": info.get("fiveYearAvgDividendYield")
            },
            "balance_sheet": {
                "totalCash": info.get("totalCash"),
                "totalDebt": info.get("totalDebt"),
                "debtToEquity": info.get("debtToEquity"),
                "currentRatio": info.get("currentRatio"),
                "quickRatio": info.get("quickRatio")
            },
            "ownership": {
                "heldPercentInstitutions": info.get("heldPercentInstitutions"),
                "heldPercentInsiders": info.get("heldPercentInsiders"),
                "floatShares": info.get("floatShares"),
                "sharesOutstanding": info.get("sharesOutstanding"),
                "shortRatio": info.get("shortRatio")
            },
            "analyst_opinions": {
                "recommendationKey": info.get("recommendationKey"),
                "numberOfAnalystOpinions": info.get("numberOfAnalystOpinions"),
                "targetMeanPrice": info.get("targetMeanPrice"),
                "targetHighPrice": info.get("targetHighPrice"),
                "targetLowPrice": info.get("targetLowPrice")
            },
            "risk_metrics": {
                "beta": info.get("beta"),
                "52WeekChange": info.get("52WeekChange"),
                "SandP52WeekChange": info.get("SandP52WeekChange")
            }
        }
    except Exception as e:
        logger.error(f"Error in fundamental analysis for {equity}: {str(e)}")
        raise APIError(f"Fundamental analysis failed: {str(e)}")

async def fetch_technical_analysis(equity):
    check_rate_limit()
    
    try:
        ticker = yf.Ticker(equity)
        hist = ticker.history(period="1y")
        if hist.empty:
            raise ValueError(f"No historical data available for {equity}")

        current_price = hist["Close"].iloc[-1]
        avg_volume = hist["Volume"].mean()

        sma_20 = hist["Close"].rolling(window=20).mean().iloc[-1]
        sma_50 = hist["Close"].rolling(window=50).mean().iloc[-1]
        sma_200 = hist["Close"].rolling(window=200).mean().iloc[-1]

        delta = hist["Close"].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.rolling(window=14).mean()
        avg_loss = loss.rolling(window=14).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs)).iloc[-1]

        high_low = hist["High"] - hist["Low"]
        high_close = (hist["High"] - hist["Close"].shift()).abs()
        low_close = (hist["Low"] - hist["Close"].shift()).abs()
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        atr = true_range.rolling(window=14).mean().iloc[-1]

        ema12 = hist["Close"].ewm(span=12, adjust=False).mean()
        ema26 = hist["Close"].ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal_line = macd.ewm(span=9, adjust=False).mean()
        macd_histogram = macd - signal_line

        price_changes = {
            "1d": hist["Close"].pct_change(periods=1).iloc[-1] * 100,
            "5d": hist["Close"].pct_change(periods=5).iloc[-1] * 100,
            "20d": hist["Close"].pct_change(periods=20).iloc[-1] * 100
        }

        ma_distances = {
            "from_20sma": ((current_price / sma_20) - 1) * 100,
            "from_50sma": ((current_price / sma_50) - 1) * 100,
            "from_200sma": ((current_price / sma_200) - 1) * 100
        }

        return {
            "price": current_price,
            "avg_volume": avg_volume,
            "moving_averages": {
                "sma_20": sma_20,
                "sma_50": sma_50,
                "sma_200": sma_200
            },
            "indicators": {
                "rsi": rsi,
                "atr": atr,
                "atr_percent": (atr / current_price) * 100,
                "macd": macd.iloc[-1],
                "macd_signal": signal_line.iloc[-1],
                "macd_histogram": macd_histogram.iloc[-1]
            },
            "trend_analysis": price_changes,
            "ma_distances": ma_distances
        }
    except Exception as e:
        logger.error(f"Error in technical analysis for {equity}: {str(e)}")
        raise APIError(f"Technical analysis failed: {str(e)}")

async def fetch_comprehensive_analysis(equity):
    check_rate_limit()
    
    try:
        fundamental_data = await fetch_fundamental_analysis(equity)
        technical_data = await fetch_technical_analysis(equity)
        
        current_price = technical_data["price"]
        target_price = fundamental_data["analyst_opinions"]["targetMeanPrice"]
        
        upside_potential = ((target_price / current_price) - 1) * 100 if target_price else None
        
        return {
            "core_valuation": {
                "current_price": current_price,
                "pe_ratio": {
                    "trailing": fundamental_data["valuation_metrics"]["trailingPE"],
                    "forward": fundamental_data["valuation_metrics"]["forwardPE"],
                    "industry_comparison": "Requires industry average PE data"
                },
                "price_to_book": fundamental_data["valuation_metrics"]["priceToBook"],
                "enterprise_to_ebitda": fundamental_data["valuation_metrics"]["enterpriseToEbitda"]
            },
            "growth_metrics": {
                "revenue_growth": fundamental_data["earnings_and_revenue"]["revenueGrowth"],
                "earnings_growth": fundamental_data["earnings_and_revenue"]["earningsGrowth"],
                "profit_margin": fundamental_data["margins_and_returns"]["profitMargins"],
                "return_on_equity": fundamental_data["margins_and_returns"]["returnOnEquity"]
            },
            "financial_health": {
                "debt_to_equity": fundamental_data["balance_sheet"]["debtToEquity"],
                "current_ratio": fundamental_data["balance_sheet"]["currentRatio"],
                "quick_ratio": fundamental_data["balance_sheet"]["quickRatio"],
                "beta": fundamental_data["risk_metrics"]["beta"]
            },
            "market_sentiment": {
                "analyst_recommendation": fundamental_data["analyst_opinions"]["recommendationKey"],
                "target_price": {
                    "mean": target_price,
                    "current": current_price,
                    "upside_potential": upside_potential
                },
                "institutional_holdings": fundamental_data["ownership"]["heldPercentInstitutions"],
                "insider_holdings": fundamental_data["ownership"]["heldPercentInsiders"]
            },
            "technical_signals": {
                "rsi": {
                    "value": technical_data["indicators"]["rsi"],
                    "signal": interpret_rsi(technical_data["indicators"]["rsi"])
                },
                "macd": {
                    "value": technical_data["indicators"]["macd"],
                    "signal": technical_data["indicators"]["macd_signal"],
                    "histogram": technical_data["indicators"]["macd_histogram"],
                    "trend": interpret_macd(
                        technical_data["indicators"]["macd"],
                        technical_data["indicators"]["macd_signal"]
                    )
                },
                "moving_averages": {
                    "sma_50": technical_data["moving_averages"]["sma_50"],
                    "sma_200": technical_data["moving_averages"]["sma_200"],
                    "price_vs_sma200": technical_data["ma_distances"]["from_200sma"],
                    "trend": interpret_ma_trend(technical_data["ma_distances"])
                }
            },
            "momentum": {
                "short_term": technical_data["trend_analysis"]["20d"],
                "year_to_date": fundamental_data["risk_metrics"]["52WeekChange"],
                "relative_strength": {
                    "vs_sp500": fundamental_data["risk_metrics"]["SandP52WeekChange"],
                    "interpretation": interpret_relative_strength(
                        fundamental_data["risk_metrics"]["52WeekChange"],
                        fundamental_data["risk_metrics"]["SandP52WeekChange"]
                    )
                }
            }
        }
    except Exception as e:
        logger.error(f"Error in comprehensive analysis for {equity}: {str(e)}")
        raise APIError(f"Comprehensive analysis failed: {str(e)}")

async def fetch_fundamental_by_groups(equity, groups):
    check_rate_limit()
    
    try:
        full_data = await fetch_fundamental_analysis(equity)
        result = {}
        for group in groups:
            if group in full_data:
                result[group] = full_data[group]
        return result
    except Exception as e:
        logger.error(f"Error in fundamental groups analysis for {equity}: {str(e)}")
        raise APIError(f"Fundamental groups analysis failed: {str(e)}")

async def fetch_technical_by_groups(equity, groups):
    check_rate_limit()
    
    try:
        full_data = await fetch_technical_analysis(equity)
        result = {}
        for group in groups:
            if group in full_data:
                result[group] = full_data[group]
        return result
    except Exception as e:
        logger.error(f"Error in technical groups analysis for {equity}: {str(e)}")
        raise APIError(f"Technical groups analysis failed: {str(e)}")

# Format complex JSON data into readable text
def format_analysis_results(data, indent=0):
    if data is None:
        return "N/A"
    
    if isinstance(data, dict):
        result = ""
        for key, value in data.items():
            formatted_key = key.replace('_', ' ').title()
            
            if isinstance(value, dict) or isinstance(value, list):
                result += f"{' ' * indent}{formatted_key}:\n{format_analysis_results(value, indent + 2)}\n"
            else:
                if isinstance(value, float):
                    if abs(value) < 0.01:  
                        formatted_value = f"{value:.2e}"
                    else:
                        formatted_value = f"{value:.2f}"
                    
                    if "percent" in key.lower() or "growth" in key.lower() or "margin" in key.lower():
                        formatted_value += "%"
                elif isinstance(value, int) and value > 1000:
                    formatted_value = f"{value:,}"  
                else:
                    formatted_value = str(value)
                
                result += f"{' ' * indent}{formatted_key}: {formatted_value}\n"
        return result
    
    elif isinstance(data, list):
        result = ""
        for i, item in enumerate(data):
            result += f"{' ' * indent}{i+1}. {format_analysis_results(item, indent + 2)}\n"
        return result
    
    else:
        return str(data)

# MCP tool definitions
@mcp.tool()
async def fundamental_data_by_category(equity: str, categories: str) -> str:
    """
    Get specific categories of fundamental data for a company.
    
    Args:
        equity: Stock ticker symbol (e.g., AAPL, MSFT, TSLA)
        categories: Comma-separated string or JSON array string of categories to retrieve (e.g., "company_info,valuation_metrics,balance_sheet")
                   Available categories: company_info, valuation_metrics, earnings_and_revenue,
                   margins_and_returns, dividends, balance_sheet, ownership, analyst_opinions, risk_metrics
    """
    try:
        # Convert string categories to list
        category_list = []
        if categories.startswith('[') and categories.endswith(']'):
            # Try to parse as JSON array
            import json
            try:
                category_list = json.loads(categories)
            except json.JSONDecodeError:
                # Fallback to comma-separated if JSON parse fails
                category_list = [cat.strip() for cat in categories.strip('[]').split(',')] 
        else:
            # Process as comma-separated string
            category_list = [cat.strip() for cat in categories.split(',')]
            
        # Continue with the list
        data = await fetch_fundamental_by_groups(equity, category_list)
        return format_analysis_results(data)
    except Exception as e:
        return f"Error retrieving fundamental data: {str(e)}"

@mcp.tool()
async def technical_data_by_category(equity: str, categories: str) -> str:
    """
    Get specific categories of technical data for a stock.
    
    Args:
        equity: Stock ticker symbol (e.g., AAPL, MSFT, TSLA)
        categories: Comma-separated string or JSON array string of categories to retrieve (e.g., "indicators,moving_averages,trend_analysis")
                   Available categories: moving_averages, indicators, trend_analysis, ma_distances, price, avg_volume
    """
    try:
        # Convert string categories to list
        category_list = []
        if categories.startswith('[') and categories.endswith(']'):
            # Try to parse as JSON array
            import json
            try:
                category_list = json.loads(categories)
            except json.JSONDecodeError:
                # Fallback to comma-separated if JSON parse fails
                category_list = [cat.strip() for cat in categories.strip('[]').split(',')] 
        else:
            # Process as comma-separated string
            category_list = [cat.strip() for cat in categories.split(',')]
            
        # Continue with the list
        data = await fetch_technical_by_groups(equity, category_list)
        return format_analysis_results(data)
    except Exception as e:
        return f"Error retrieving technical data: {str(e)}"

@mcp.tool()
async def comprehensive_analysis(equity: str) -> str:
    """
    Get complete investment analysis combining both fundamental and technical factors.
    Provides a holistic view of a stock with interpreted signals, valuation assessment,
    growth metrics, financial health indicators, and momentum analysis with clear buy/sell signals.
    
    Args:
        equity: Stock ticker symbol (e.g., AAPL, MSFT, TSLA)
    """
    try:
        data = await fetch_comprehensive_analysis(equity)
        return format_analysis_results(data)
    except Exception as e:
        return f"Error retrieving comprehensive analysis: {str(e)}"

def main():
    parser = argparse.ArgumentParser(description='Run Financial Analysis MCP server')
    parser.add_argument('--port', type=int, default=8086, help='Port to run the server on')
    
    args = parser.parse_args()
    
    mcp.settings.port = args.port
    logger.info(f"Starting Financial Analysis server with Streamable HTTP transport on port {args.port}")
    mcp.run(transport='streamable-http')

if __name__ == "__main__":
    main()
