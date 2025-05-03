from typing import Dict, Any
from .node import Node, AgentState


class PortfolioManagementNode(Node):
    def __call__(self, state: AgentState) -> Dict[str, Any]:

        data = state['data']
        data['name'] = "PortfolioManagementNode"
        return state
