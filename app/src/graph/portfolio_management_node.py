import os
from typing import Dict, Any, List
import json
from langchain_core.messages import HumanMessage
from src.utils.logger import setup_logger
from src.utils.binance_chart_provider import get_chart
from .base_node import BaseNode, AgentState
from graph import show_agent_reasoning
from src.llm import get_azure_openai_client
from pathlib import Path
from datetime import datetime
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed


client = get_azure_openai_client() 
logger = setup_logger()

BASE_DIR = Path(__file__).resolve().parent.parent

def load_and_render_prompt(path: str, variables: Dict[str, Any]) -> str:
    with open(path, "r", encoding="utf-8") as f: 
        template = f.read()
    for key, value in variables.items():
        if not isinstance(value, str):
            value = json.dumps(value, indent=2)
        template = template.replace(f"{{{{{key}}}}}", value)
    return template


class PortfolioManagementNode(BaseNode):
    def __call__(self, state: AgentState) -> Dict[str, Any]:
        """Makes final trading decisions and generates orders for multiple tickers"""

        data = state.get('data', {})
        data['name'] = "PortfolioManagementNode"
        # Get the portfolio and analyst signals
        portfolio = data.get("portfolio", {})
        end_date = data.get("end_date")
        analyst_signals = data.get("analyst_signals", {})
        tickers = data.get("tickers", [])

        # Get position limits, current prices, and signals for every ticker
        position_limits = {}
        current_prices = {}
        max_shares = {}
        signals_by_ticker = {}
        for ticker in tickers:

            # Get position limits and current prices for the ticker
            risk_data = analyst_signals.get("risk_management_agent", {}).get(ticker, {})
            position_limits[ticker] = risk_data.get("remaining_position_limit", 0.0)
            current_prices[ticker] = risk_data.get("current_price", 0.0)

            # Calculate maximum shares allowed based on position limit and price
            if current_prices[ticker] > 0.0:
                max_shares[ticker] = float(position_limits[ticker] / current_prices[ticker])
            else:
                max_shares[ticker] = 0.0

            # Get signals for the ticker
            ticker_signals = {}
            for agent, signals in analyst_signals.items():
                if agent == "technical_analyst_agent" and ticker in signals:
                    ticker_signals[agent] = signals[ticker]

            signals_by_ticker[ticker] = ticker_signals

        # Generate the trading decision
        result = generate_trading_decision(
            tickers=tickers,
            signals_by_ticker=signals_by_ticker,
            current_prices=current_prices,
            end_date=end_date,
            max_shares=max_shares,
            portfolio=portfolio,
            model_name=state["metadata"]["model_name"],
            model_provider=state["metadata"]["model_provider"],
        )

        # Create the portfolio management message
        message = HumanMessage(
            content=json.dumps(result.get("decisions", {})),
            name="portfolio_management",
        )

        if state["metadata"]["show_reasoning"]:
            show_agent_reasoning(result.get("decisions"),
                                 "Portfolio Management Agent")

        return {
            "messages": [message],
            "data": state["data"],
        }

        # return state


def generate_trading_decision(
        tickers: List[str],
        signals_by_ticker: Dict[str, Dict[str, Any]],
        current_prices: Dict[str, float],
        end_date: datetime,
        max_shares: Dict[str, float],
        portfolio: Dict[str, float],
        model_name: str,
        model_provider: str):
    """Attempts to get a decision from the LLM with retry logic"""
    # Create the prompt template
    
    prompt_vars = {
        "signals_by_ticker": signals_by_ticker,
        "current_prices": current_prices,
        "portfolio_cash": f"{portfolio.get('available_USDC', 0.0):.2f}",
        "available_margin_USDC": f"{portfolio.get('available_margin_USDC', 0.0):.2f}",
        "portfolio_positions": portfolio.get("positions", {})
    }

    prompt_path_blue_black = BASE_DIR / "prompts" / "rule_blue_black.txt"
    user_prompt_blue_black = load_and_render_prompt(prompt_path_blue_black, prompt_vars)
    
    prompt_path_green_red = BASE_DIR / "prompts" / "rule_green_red.txt"
    user_prompt_green_red = load_and_render_prompt(prompt_path_green_red, prompt_vars)
    
    
    end_date_ts = int(end_date.timestamp() * 1000)
    symbol_chart_base64_1m_blue_black = get_chart("ETHUSDC", "1m", ["#011AFF", "#000000"], 240, end_date_ts)
    symbol_chart_base64_5m_blue_black = get_chart("ETHUSDC", "5m", ["#011AFF", "#000000"], 60, end_date_ts)
    
    symbol_chart_base64_1m_green_red = get_chart("ETHUSDC", "1m", ["#1FFF01", "#FF0000"], 240, end_date_ts)
    symbol_chart_base64_5m_green_red = get_chart("ETHUSDC", "5m",  ["#1FFF01", "#FF0000"], 60, end_date_ts)

    logger.debug(f"[ℹ️] Available USDC: {portfolio.get('available_USDC', 0.0):.2f} tickers...")
    logger.debug(f"[ℹ️] Available margin USDC: {portfolio.get('available_margin_USDC', 0.0):.2f}")
    logger.debug(f"[ℹ️] Current prices: {current_prices}")
    logger.debug(f"Portfolio positions: {json.dumps(portfolio.get('positions', {}), indent=2)}")
    logger.debug(f"Portfolio equity: {portfolio.get('equity', 0.0):.2f}")
   
    
    max_retries = 10
    
    def _call_llm(user_prompt, symbol_chart_base64_1m, symbol_chart_base64_5m):
        for attempt in range(1, max_retries + 1):
            resp = client.chat.completions.create(
                model=model_name,
                messages=[
                {"role": "user", 
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {"type": "text", "text": "Candlestick chart in 1-minute intervals for ETHUSDC. Includes Bollinger Bands (Upper, Mid, Lower), short-term moving averages (MA5, MA10), volume bars, MACD with signal line and histogram, and multi-period RSI (6, 12, 24):"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "data:image/png;base64," + symbol_chart_base64_1m
                            },
                        },
                        {"type": "text", "text": "Candlestick chart in 5-minute intervals for ETHUSDC. Includes Bollinger Bands (Upper, Mid, Lower), short-term moving averages (MA5, MA10), volume bars, MACD with signal line and histogram, and multi-period RSI (6, 12, 24):"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "data:image/png;base64," + symbol_chart_base64_5m
                            },
                        },
                    ],
                },
            ],
        )
            content = resp.choices[0].message.content.replace("```json", "").replace("```", "").strip()
            if not content:
                continue
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                continue
            decisions = data.get("decisions")
            if not isinstance(decisions, dict):
                continue
            d = decisions.get("ETHUSDC", {})
            if (
                d.get("operation") in {"open_long", "close_long", "open_short", "close_short", "hold"}
                and isinstance(d.get("quantity"), (int, float))
                and isinstance(d.get("confidence"), (int, float))
            ):
                return data
        return None
    
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(_call_llm, user_prompt_blue_black, symbol_chart_base64_1m_blue_black, symbol_chart_base64_5m_blue_black),
            executor.submit(_call_llm, user_prompt_green_red, symbol_chart_base64_1m_green_red, symbol_chart_base64_5m_green_red),
        ]
        
        results = [f.result() for f in as_completed(futures)]
    results = [r for r in results if r and "ETHUSDC" in r.get("decisions", {})]
    if len(results) < 2:
        raise ValueError("❌ Less than two valid LLM responses received.")

    d1 = results[0]["decisions"]["ETHUSDC"]
    d2 = results[1]["decisions"]["ETHUSDC"]

    if d1["operation"] == d2["operation"]:
        best = results[0] if d1["quantity"] >= d2["quantity"] else results[1]
    else:
        results[0]["decisions"]["ETHUSDC"]["operation"] = "hold"
        best = results[0]

    if best["decisions"]["ETHUSDC"]["operation"] != "hold":
        output_dir = BASE_DIR / "output"
        output_dir.mkdir(exist_ok=True)
        for tf in ["1m", "5m"]:
            fname_green_red = output_dir / f"graph_{tf}_{end_date.strftime('%Y%m%d_%H%M%S')}_{best["decisions"]["ETHUSDC"]["operation"]}_green_red.png"
            with open(fname_green_red, "wb") as f:
                b64 = symbol_chart_base64_1m_green_red if tf == "1m" else symbol_chart_base64_5m_green_red
                f.write(base64.b64decode(b64))
            fname_blue_black = output_dir / f"graph_{tf}_{end_date.strftime('%Y%m%d_%H%M%S')}_{best["decisions"]["ETHUSDC"]["operation"]}_blue_black.png"
            with open(fname_blue_black, "wb") as f:
                b64 = symbol_chart_base64_1m_blue_black if tf == "1m" else symbol_chart_base64_5m_blue_black
                f.write(base64.b64decode(b64))
        fname = output_dir / f"decisions_{end_date.strftime('%Y%m%d_%H%M%S')}_{best["decisions"]["ETHUSDC"]["operation"]}.txt"
        with open(fname, "w") as f:
            json.dump(best["decisions"], f)

    return best