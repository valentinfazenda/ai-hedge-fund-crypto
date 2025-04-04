
from datetime import datetime
import pandas as pd
from src.gateway.binance.client import Client


from src.data.cache import get_cache
from src.data.models import (
    Price
)


# Global cache instance
_cache = get_cache()
_binance_client = Client()

def get_prices(ticker: str, start_date: str, end_date: str) -> list[Price]:
    """Fetch price data from cache or API."""
    # Check cache first
    if cached_data := _cache.get_prices(ticker):
        # Filter cached data by date range and convert to Price objects
        filtered_data = [Price(**price) for price in cached_data if start_date <= price["time"] <= end_date]
        if filtered_data:
            return filtered_data

    response = _binance_client.get_historical_klines(symbol=ticker, interval=Client.KLINE_INTERVAL_1DAY,
                                          start_str=start_date, end_str=end_date)
    prices = []
    if isinstance(response, list):
        for item in response:
            price = Price(**{
                "time":  datetime.utcfromtimestamp(item[0]/1000).strftime('%Y-%m-%d %H:%M:%S'),
                'open': float(item[1]),
                'high': float(item[2]),
                'low': float(item[3]),
                'close': float(item[4]),
                'volume': float(item[5]),
            })
            prices.append(price)

    if not prices:
        return []

    # Cache the results as dicts
    _cache.set_prices(ticker, [p.model_dump() for p in prices])
    return prices


def prices_to_df(prices: list[Price]) -> pd.DataFrame:
    """Convert prices to a DataFrame."""
    df = pd.DataFrame([p.model_dump() for p in prices])
    df["Date"] = pd.to_datetime(df["time"])
    df.set_index("Date", inplace=True)
    numeric_cols = ["open", "close", "high", "low", "volume"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df.sort_index(inplace=True)
    return df

# Update the get_price_data function to use the new functions
def get_price_data(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    prices = get_prices(ticker, start_date, end_date)
    return prices_to_df(prices)