"""
start node
"""

from datetime import datetime, timedelta
from typing import Dict, Any

from .node import Node, AgentState
from src.utils import BinanceDataProvider

# Initialize data provider
data_provider = BinanceDataProvider()


class StartNode(Node):
    """
    start node
    """
    def __call__(self, state: AgentState) -> Dict[str, Any]:
        data = state['data']
        data['name'] = "StartNode"
        return state
