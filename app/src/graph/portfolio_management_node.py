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
    print (f"Portfolio: {portfolio}")
    
    system_prompt = """
    You are a professional cryptocurrency portfolio manager operating in a 24 / 7, highly-volatile market.
    Your mandate:
    • Preserve capital and grow risk-adjusted return (Sharpe, Sortino) over the long run.  
    • Size every trade so that the portfolio’s 1-day 99 % Expected Shortfall never exceeds a configurable limit.  
    • Respect exchange margin, position and notional caps at all times.  
    • Prefer liquidity, low slippage routes and stable-coin settlement when cash-like exposure is required.  
    • React swiftly to regime shifts triggered by on-chain activity, funding-rate spikes, large liquidations or macro headlines.  
    Think first, then answer only with a valid JSON object.
    
    Inputs:
    - signals_by_ticker: dictionary of ticker → signals
    - max_shares: maximum shares allowed per ticker
    - portfolio_cash: current cash in portfolio
    - portfolio_positions: current positions (both long and short)
    - current_prices: current prices for each ticker
    - margin_requirement: current margin requirement for short positions (e.g., 0.5 means 50%)
    - total_margin_used: total margin currently in use
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
    cash: 
    {portfolio.get('cash', 0.0):.2f}
    positions: 
    {json.dumps(portfolio.get('positions', {}), indent=2)}
    margin_requirement: 
    {portfolio.get('margin_requirement', 0.0):.2f}
    margin_used: 
    {portfolio.get('margin_used', 0.0):.2f}

    ⚠️ Decisions are margin-based:
    - **Trades can exceed available cash**, as long as margin constraints are respected.
    - Ensure all actions comply with **available margin**, **risk rules**, and **volatility regime constraints**.

    Available Actions:
    - "buy": Open or add to long position
    - "sell": Close or reduce long position
    - "short": Open or add to short position
    - "cover": Close or reduce short position
    - "hold": No action

    Rules:
    - For long positions:
    * Only buy if enough **available cash or margin**.
    * Only sell if currently holding long shares.
    * Sell quantity ≤ current long position.
    * Buy quantity ≤ max_shares[ticker].

    - For short positions:
    * Only short if sufficient **available margin**.
    * Only cover if currently holding short shares.
    * Cover quantity ≤ current short position.
    * Short quantity must respect margin requirements (position value × margin_requirement).

    # Decision rubric (follow strictly, in order)
    1. Build a **conviction score** per ticker combining:
    – multi-time-frame consensus  
    – signal confidence (higher resolution ⇒ higher weight)  
    – momentum direction & strength  
    – realised/implied volatility, funding  
    – liquidity & slippage cost

    2. **Buy** only if conviction ≥ 50 AND    
    Else: "hold".

    3. **Sell** if long position exists AND  
    • price ≥ cost_basis × 1.03 (profit >3%), _or_  
    • price −4% in 30m OR 1h/2h with bearish signal

    4. Keep ≥20% free equity (cash or stable assets).

    5. **Short** only if conviction ≥ 50
    Else: "hold".

    6. **Cover** if short exists AND  
    • price ≤ cost_basis × 0.97 (profit >3%), _or_  
    • price +2% in 30m OR +4% in 1h/2h with bullish signal

    # Output format:
    Return only valid JSON with this strict structure:

    {{ "decisions": {{ 
        "TICKER": {{
        "action":"buy"|"sell"|"short"|"cover"|"hold",
        "quantity": float,
        "confidence": float,
        "reasoning": "string"
        }},
        ...
    }} }}
    """
    
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
