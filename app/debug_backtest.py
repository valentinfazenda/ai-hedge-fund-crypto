import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
from src.backtest.backtester import Backtester
from src.utils.logger import setup_logger
import json

logger = setup_logger()

if __name__ == "__main__":

    backtester = Backtester(
        primary_interval="12h",
        intervals=["12h", "2h", "1h", "30m", "15m", "5m"],
        tickers= ["ETHUSDC"],
        start_date="2025-05-23",
        end_date="2025-05-24",
        initial_capital=10,
        initial_margin_requirement=0.2,
        strategies=['MacdStrategy', "RSIStrategy"],
        show_agent_graph="false",
        show_reasoning="false",
    )
    
    logger.info("Starting backtest...")
    logger.info(f"Initial Capital: {backtester.initial_capital}")

    backtester.execute_trade("ETHUSDC", "short", 2, 1)

    logger.info("Executed short trade (2 for 1)")
    logger.info(f"Portfolio after short: {json.dumps(backtester.portfolio, indent=2)}")

    backtester.execute_trade("ETHUSDC", "cover", 1, 0.5)

    logger.info("Executed cover trade (1 for 0.5)")
    logger.info(f"Final Portfolio: {json.dumps(backtester.portfolio, indent=2)}")

    current_price = {"ETHUSDC": 1}
    portfolio_value = backtester.calculate_portfolio_value(current_price)
    logger.info(f"Portfolio Value at current price: {portfolio_value}")