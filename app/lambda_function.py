import os
import sys
from datetime import datetime

# Include src in the path
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from src.utils import settings
from src.agent import Agent
from src.backtest.backtester import Backtester
from src.utils.binance_order_executor import place_binance_order, build_portfolio_from_binance_assets

def lambda_handler(event, context):
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
        
        return {
            "statusCode": 200,
            "body": "Backtest complete.",
            "performance": performance_metrics
        }


    else:
        portfolio = build_portfolio_from_binance_assets(settings)

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
        
        
        print(result.get('decisions'))
        decisions = result.get("decisions", {})

        for symbol, decision in decisions.items():
            place_binance_order(symbol,  decision["operation"], decision["quantity"])

        return {
            "statusCode": 200,
            "body": {
                "portfolio": str(portfolio),
                "decisions": decisions
            }
        }
