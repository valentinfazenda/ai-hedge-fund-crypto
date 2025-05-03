from dotenv import load_dotenv
from utils import settings

from agent import Workflow, Agent
from src.backtest.backtester import Backtester

load_dotenv()


if __name__ == "__main__":

    portfolio = {
        "cash": settings.initial_cash,  # Initial cash amount
        "margin_requirement": settings.margin_requirement,  # Initial margin requirement
        "margin_used": 0.0,  # total margin usage across all short positions
        "positions": {
            ticker: {
                "long": 0,  # Number of shares held long
                "short": 0,  # Number of shares held short
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

    backtester = Backtester(
        primary_interval=settings.primary_interval,
        intervals=settings.signals.intervals,
        tickers=settings.signals.tickers,
        start_date=settings.start_date,
        end_date=settings.end_date,
        initial_capital=settings.initial_cash,
        strategies=settings.signals.strategies,
    )

    print("Starting backtest...")
    # Agent.run(tickers=settings.signals.tickers,
    #           start_date=settings.start_date,
    #           end_date=settings.end_date,
    #           portfolio=portfolio,
    #           strategies=settings.signals.strategies,
    #           show_reasoning=settings.show_reasoning,
    #           )
