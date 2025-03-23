from src.backtester import Backtester
from src.graph import run_hedge_fund


if __name__ == '__main__':

    backtester = Backtester(
        agent=run_hedge_fund,
        tickers=['BTCUSDT'],
        start_date='2025-1-1',
        end_date='2025-3-1',
        initial_capital=100000,
        selected_analysts=['technical_analyst_agent'],
        initial_margin_requirement=0,
    )

    performance_metrics = backtester.run_backtest()
    performance_df = backtester.analyze_performance()
