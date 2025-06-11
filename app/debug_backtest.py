import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
from src.backtest.backtester import Backtester
import json

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
    print("Starting backtest...")
    print(f"Initial Capital: {backtester.initial_capital}")
    
    # backtester.execute_trade("ETHUSDC", "buy", 2, 1)
    
    # print ("Analytics bought 2 for 1:")
    # print(f"Portfolio: {backtester.portfolio}")
    
    # backtester.execute_trade("ETHUSDC", "sell", 1, 2)
    
    # print ("Analytics sell 1 for 2:")
    # print(f"Final Portfolio: {backtester.portfolio}")
    backtester.execute_trade("ETHUSDC", "short", 2, 1)
    
    print ("Analytics bought 2 for 1:")
    print(f"Portfolio: {backtester.portfolio}")
    
    backtester.execute_trade("ETHUSDC", "cover", 1, 0.5)
    
    print ("Analytics sell 1 for 2:")
    print(f"Final Portfolio: {backtester.portfolio}")
    
    current_price = {}
    current_price["ETHUSDC"] = 1
    print(f"Portolio Value: {backtester.calculate_portfolio_value(current_price)}")