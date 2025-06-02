import os
import sys
from datetime import datetime

# Inclure src dans le path
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from src.utils import settings
from src.agent import Agent
from src.backtest.backtester import Backtester
from src.utils.kucoin_order_executor import place_kucoin_order, build_portfolio_from_kucoin_assets

def lambda_handler(event, context):
    if settings.mode == "backtest":
        backtester = Backtester(
            primary_interval=settings.primary_interval,
            intervals=settings.signals.intervals,
            tickers=settings.signals.tickers,
            start_date=settings.start_date,
            initial_margin_requirement=settings.margin_requirement,
            end_date=settings.end_date,
            initial_capital=settings.initial_cash,
            strategies=settings.signals.strategies,
            show_agent_graph=settings.show_agent_graph,
            show_reasoning=settings.show_reasoning,
        )
        performance_metrics = backtester.run_backtest()
        performance_df = backtester.analyze_performance()
        return {
            "statusCode": 200,
            "body": "Backtest complete.",
            "performance": performance_metrics
        }
    else:
        portfolio = build_portfolio_from_kucoin_assets(settings)
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

        decisions = result.get("decisions", {})

        for symbol, decision in decisions.items():
            place_kucoin_order(symbol, decision["action"], decision["quantity"])

        return {
            "statusCode": 200,
            "body": {
                "portfolio": str(portfolio),
                "decisions": decisions
            }
        }
