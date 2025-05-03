from typing import Dict, Any
from .state import AgentState
from .node import Node, AgentState


class RiskManagementNode(Node):
    def __call__(self, state: AgentState) -> Dict[str, Any]:

        data = state['data']
        data['name'] = "RiskManagementNode"
        return state
