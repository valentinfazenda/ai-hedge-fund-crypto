import os
from typing import Dict, Any, List
import json
from langchain_core.messages import HumanMessage
from src.utils.logger import setup_logger
from .base_node import BaseNode, AgentState
from graph import show_agent_reasoning
from src.llm import get_azure_openai_client
from pathlib import Path


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

    prompt_path = BASE_DIR / "prompts" / "rule.txt"
    user_prompt = load_and_render_prompt(prompt_path, prompt_vars)
    
    logger.debug(f"Prompting {user_prompt}")
    logger.debug(f"[ℹ️] Available USDC: {portfolio.get('available_USDC', 0.0):.2f} tickers...")
    logger.debug(f"[ℹ️] Available margin USDC: {portfolio.get('available_margin_USDC', 0.0):.2f}")
    logger.debug(f"[ℹ️] Current prices: {current_prices}")
    logger.debug(f"Portfolio positions: {json.dumps(portfolio.get('positions', {}), indent=2)}")
    logger.debug(f"Portfolio equity: {portfolio.get('equity', 0.0):.2f}")
   
    
    max_retries = 10
    valid_ops = {"open_long", "close_long", "open_short", "close_short", "hold"}

    for attempt in range(1, max_retries + 1):
        resp = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "user", "content": user_prompt},
            ],
        )
        content = resp.choices[0].message.content.replace("```json", "").replace("```", "").strip()
        if not content:
            logger.warning(f"⚠️ Attempt {attempt}: Empty response")
            continue
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            logger.warning(f"⚠️ Attempt {attempt}: Invalid JSON\n{content}")
            continue

        decisions = data.get("decisions")
        logger.info (f"Attempt {attempt}: decisions = {decisions}")
        if not isinstance(decisions, dict):
            logger.warning(f"⚠️ Attempt {attempt}: 'decisions' missing or not a dict")
            continue

        def _valid(d):
            return (
                isinstance(d, dict)
                and d.get("operation") in valid_ops
                and isinstance(d.get("quantity"), (int, float))
                and isinstance(d.get("confidence"), (int, float))
            )

        if all(_valid(v) for v in decisions.values()):
            return data

        logger.error(f"⚠️ Attempt {attempt}: Malformed decisions\n{decisions}")

    raise ValueError("❌ No valid response from LLM after multiple retries.")
