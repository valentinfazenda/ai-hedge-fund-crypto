import os
from typing import Dict, Any, List
import json
from langchain_core.messages import HumanMessage
from .base_node import BaseNode, AgentState
from graph import show_agent_reasoning
from src.llm import get_azure_openai_client


client = get_azure_openai_client() 


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

        # Print the decision if the flag is set
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
    
    system_prompt = """
    You are a professional cryptocurrency portfolio manager operating in a 24 / 7, highly-volatile market.
    Your mandate:
    • Preserve capital and grow risk-adjusted return (Sharpe, Sortino) over the long run.  
    • Size every trade so that the portfolio’s 1-day 99 % Expected Shortfall never exceeds a configurable limit.  
    • Respect exchange margin, position and notional caps at all times.  
    • Prefer liquidity, low slippage routes and stable-coin settlement when cash-like exposure is required.  
    • React swiftly to regime shifts triggered by on-chain activity, funding-rate spikes, large liquidations or macro headlines.  
    Think first, then answer only with a valid JSON object.
    """

    user_prompt = f"""
    # Inputs
    Signals by ticker
    {json.dumps(signals_by_ticker, indent=2)}

    Real-time mid-prices
    {json.dumps(current_prices, indent=2)}

    Max size per ticker (absolute units)
    {json.dumps(max_shares, indent=2)}

    Portfolio snapshot
    cash: {portfolio.get('cash', 0.0):.2f}
    positions: {json.dumps(portfolio.get('positions', {}), indent=2)}
    margin_requirement: {portfolio.get('margin_requirement', 0.0):.2f}
    margin_used: {portfolio.get('margin_used', 0.0):.2f}

    # Decision rubric (follow in order)
    1. Build a conviction score per ticker combining:
    – multi-time-frame consensus strength  
    – signal confidence weighting (higher resolution ⇢ higher weight)  
    – momentum direction & magnitude  
    – recent realised / implied volatility and funding  
    – liquidity & slippage cost
    2. Reject low-conviction (<30 %) ideas unless risk can be hedged cheaply.
    3. If volatility regime exceeds 4× its 12-hour average and the price is dropping sharply, aggressively reduce gross exposure by at least 30 %. Do not hesitate to exit all positions if signals turn bearish.
    4. If volatility is high but price is rising steadily across timeframes with strong bullish signals, maintain or increase exposure within position limits.
    5. Use cash/stable-coin buffers to maintain ≥20 % unencumbered equity.
    6. If a price drops >2 % in <10 min and signals turn bearish, prioritise exit or short.
    7. Keep JSON output deterministic, no extra keys, floats with max 6 decimals.

    
    Provide the answer without any additional text or explanations. The answer will be processed by the system as a json, any other format will be rejected.

    Output strictly in JSON with the structure:
    {{ "decisions": {{ 
        "TICKER": {{
        "action": "buy/sell/none",
        "quantity": float,
        "confidence": float,
        "reasoning": "string"
        }},
        ...
    }} }}
    """

    print (f" User prompt: {user_prompt}")
    
    max_retries = 10
    for attempt in range(1, max_retries + 1):
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        content = response.choices[0].message.content.replace("```json", "").replace("```", "").strip()

        if not content:
            print(f"⚠️ Attempt {attempt}: Empty response from LLM")
            continue

        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            print(f"⚠️ Attempt {attempt}: Invalid JSON response:\n{content}")
            continue

        # Validate structure
        decisions = result.get("decisions")
        if isinstance(decisions, dict) and all(
            isinstance(v, dict) and "action" in v and "quantity" in v
            for v in decisions.values()
        ):
            return result

        print(f"⚠️ Attempt {attempt}: Malformed decisions object:\n{decisions}")

    raise ValueError("❌ Failed to get a valid response from LLM after multiple retries.")
