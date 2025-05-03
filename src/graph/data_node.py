"""
Data Fetching Module

This module handles the first step in the workflow: fetching data from the data provider.
"""

from datetime import datetime, timedelta
from typing import Dict, Any

from .state import AgentState
from src.utils import BinanceDataProvider, Interval
from .node import Node, AgentState

# Initialize data provider
data_provider = BinanceDataProvider()


class DataNode(Node):
    def __init__(self, interval: Interval = Interval.DAY_1):
        self.interval = interval

    def __call__(self, state: AgentState) -> Dict[str, Any]:
        """
        Fetch data for all required timeframes using the BinanceDataProvider.

        Args:
            state: The current state with symbol information

        Returns:
            Updated state with timeframes data
        """
        data = state['data']
        data['name'] = "DataNode"
        print(state)
        return state

        # print("fetching data: ", state)
        # symbol = state["symbol"]
        # timeframes = list(TIMEFRAME_WEIGHTS.keys())
        #
        # # Default to the configured number of days of data
        # try:
        #     # Use our data provider to get multi-timeframe data
        #     timeframes_data = data_provider.get_latest_multi_timeframe_data(
        #         symbol=symbol,
        #         timeframes=timeframes,
        #     )
        #
        #     # Check if we got data for all timeframes
        #     missing_timeframes = set(timeframes) - set(timeframes_data.keys())
        #     if missing_timeframes:
        #         print(f"Warning: Missing data for timeframes: {missing_timeframes}")
        #
        #     return {"timeframes": timeframes_data}
        #
        # except Exception as e:
        #     print(f"Error fetching data: {e}")
        #     return {"timeframes": {}}
