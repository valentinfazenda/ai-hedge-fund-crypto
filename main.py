import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
from dotenv import load_dotenv
from src.utils import settings
from datetime import datetime
from src.agent import Agent
from src.backtest.backtester import Backtester
from src.utils.dydx_client import get_dydx_client


if __name__ == "__main__":

    if settings.mode == "backtest":
        backtester = Backtester(
            primary_interval=settings.primary_interval,
            intervals=settings.signals.intervals,
            tickers=settings.signals.tickers,
            start_date=settings.start_date,
            end_date=settings.end_date,
            initial_capital=settings.initial_cash,
            strategies=settings.signals.strategies,
            show_agent_graph=settings.show_agent_graph,
            show_reasoning=settings.show_reasoning,
        )
        print("Starting backtest...")
        performance_metrics = backtester.run_backtest()
        performance_df = backtester.analyze_performance()

    else:
        portfolio = {
            "cash": settings.initial_cash,  # Initial cash amount
            "margin_requirement": settings.margin_requirement,  # Initial margin requirement
            "margin_used": 0.0,  # total margin usage across all short positions
            "positions": {
                ticker: {
                    "long": 0.0,  # Number of shares held long
                    "short": 0.0,  # Number of shares held short
                    "long_cost_basis": 0.0,  # Average cost basis for long positions
                    "short_cost_basis": 0.0,  # Average price at which shares were sold short
                    "short_margin_used": 0.0,  # Dollars of margin used for this ticker's short
                }
                for ticker in settings.signals.tickers
            },
            "realized_gains": {
                ticker: {
                    "long": 0.0,  # Realized gains from long positions
                    "short": 0.0,  # Realized gains from short positions
                }
                for ticker in settings.signals.tickers
            },
        }

        result = Agent.run(
            primary_interval=settings.primary_interval,
            intervals=settings.signals.intervals,
            tickers=settings.signals.tickers,
            end_date=datetime.now(),
            portfolio=portfolio,
            strategies=settings.signals.strategies,
            show_reasoning=settings.show_reasoning,
            show_agent_graph=settings.show_agent_graph
        )
        # print(result)
        
        
        print(result.get('decisions'))
        
        dydx_client = get_dydx_client()
        decisions = result.get("decisions", {})

        for symbol, decision in decisions.items():
            action = decision.get("action")
            quantity = float(decision.get("quantity", 0.0))

            # Map symbol from "ETHUSDT" ➝ "ETH-USD"
            dydx_market = symbol.replace("USDT", "USD").replace("USDC", "USD")

            if quantity <= 0.0:
                continue

            if action == "hold":
                print(f"ℹ️ {symbol}: HOLD – no action taken.")
                continue

            side = None
            if action in ("buy", "cover"):
                side = "buy"
            elif action in ("sell", "short"):
                side = "sell"

            if side:
                try:
                    print(f"🟢 Placing {action.upper()} on dYdX: {dydx_market} – Qty: {quantity}")
                    response = dydx_client.private.create_order(
                        position_id=dydx_client.private.get_account()["account"]["positionId"],
                        market=dydx_market,
                        side=side,
                        type="market",
                        size=str(quantity),  # must be str for dydx
                        price="0",  # ignored for market
                        limit_fee="0.005",  # 0.05% max taker fee
                        cancel_after="day",
                        time_in_force="FOK"
                    )
                    print(f"✅ dYdX {action.upper()} executed: ID = {response['order']['id']}")
                except Exception as e:
                    print(f"❌ Failed to execute {action.upper()} on dYdX for {symbol}: {str(e)}")
            else:
                print(f"⚠️ Unknown action '{action}' for {symbol}. Skipping.")
