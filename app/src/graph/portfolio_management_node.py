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
    You are a professional cryptocurrency portfolio manager operating in a 24/7, highly-volatile market.
    Mandate
    • Preserve capital and maximise risk-adjusted return (Sharpe, Sortino).  
    • Keep 1-day 99 % Expected Shortfall under the configured limit.  
    • Always respect exchange margin, position and notional caps.  
    • Prefer liquid venues, low slippage routes and stable-coin settlement for cash-like exposure.  
    • React swiftly to regime shifts (on-chain activity, funding spikes, liquidations, macro headlines).  
    Think first, then answer ONLY with a valid JSON object.

    Inputs
    • signals_by_ticker – dict ticker → signals  
    • current_prices – dict ticker → price  
    • max_shares – dict ticker → float  
    • portfolio_cash – USDC available  
    • portfolio_positions – current open positions (long & short)  
    • margin_requirement – fraction for shorts  
    • total_margin_used – notional currently borrowed

    Available operations
    • open_long   – open / add to a long position  
    • open_short  – open / add to a short position  
    • close_long  – close / reduce an existing long position  
    • close_short – close / reduce an existing short position  
    • hold        – no action

    Rules
    LONG
    open_long: require cash and/or available margin  
    close_long: only if a long exists; quantity ≤ current long size
    SHORT
    open_short: require available margin ((qty×price)×margin_requirement)  
    close_short: only if a short exists; quantity ≤ current short size

    Conviction score per ticker combines
    • multi-time-frame consensus  
    • signal confidence (higher resolution ⇒ higher weight)  
    • momentum direction & strength  
    • realised / implied vol, funding

    Output JSON ONLY. No extra text.
    
    """

    user_prompt = f"""
    signals_by_ticker:
    {json.dumps(signals_by_ticker, indent=2)}

    current_prices:
    {json.dumps(current_prices, indent=2)}

    portfolio_cash: {portfolio.get('available_USDC', 0.0):.2f}
    
    available_margin_USDC: {portfolio.get('available_margin_USDC', 0.0):.2f}
    
    portfolio_positions:
    {json.dumps(portfolio.get('positions', {}), indent=2)}

        
    • If no position exists and market shows a bearish or bullish shorterm signal, open_long or open_short with quantity*current_prices < [available_margin_USDC]
    

    # Output format (strict)
    {{
    "decisions": {{
        "TICKER": {{
        "operation": "open_long" | "open_short" | "close_long" | "close_short" | "hold",
        "quantity": float,
        "confidence": 0-100,
        "reasoning": "string explaining the choice",
        "side": "long" | "short"        # mandatory when operation != hold
        }},
        ...
    }}
    }}
    """
    
    # print(f"Prompting {user_prompt}")
    # print (f"[ℹ️] Available USDC : {portfolio.get('available_USDC', 0.0):.2f} tickers...")
    # print (f"[ℹ️] Available margin USDC: {portfolio.get('available_margin_USDC', 0.0):.2f}")
    # print (f"[ℹ️] Current_prices: {current_prices}")
    # print (f"portfolio positions: {json.dumps(portfolio.get('positions', {}), indent=2)}")
    # print (f"portfolio equity: {portfolio.get('equity', 0.0):.2f}")    
    
    max_retries = 10
    valid_ops = {"open_long", "close_long", "open_short", "close_short", "hold"}

    for attempt in range(1, max_retries + 1):
        resp = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = resp.choices[0].message.content.replace("```json", "").replace("```", "").strip()
        if not content:
            print(f"⚠️ Attempt {attempt}: Empty response")
            continue
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            print(f"⚠️ Attempt {attempt}: Invalid JSON\n{content}")
            continue

        decisions = data.get("decisions")
        print (f"Attempt {attempt}: decisions = {decisions}")
        if not isinstance(decisions, dict):
            print(f"⚠️ Attempt {attempt}: 'decisions' missing or not a dict")
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

        print(f"⚠️ Attempt {attempt}: Malformed decisions\n{decisions}")

    raise ValueError("❌ No valid response from LLM after multiple retries.")
