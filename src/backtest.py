import os
# Set TERM environment variable if not already set
if 'TERM' not in os.environ:
    os.environ['TERM'] = 'xterm-256color'

from src.backtester.backtester import Backtester
from src.graph import run_hedge_fund


if __name__ == '__main__':
    os.environ["TERM"] = "xterm"
    from dotenv import load_dotenv
    load_dotenv()

    # from binance.client import Client
    # _binance_client = Client()
    # data = _binance_client.get_historical_klines(symbol='BTCUSDT', interval=Client.KLINE_INTERVAL_15MINUTE,
    #                                              start_str='2025-1-1', end_str='2025-2-1')
    #
    # print(data, len(data))
    #
    # exit()

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
