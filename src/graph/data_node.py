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
        return state

