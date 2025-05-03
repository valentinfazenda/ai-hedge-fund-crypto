# put your strategies here.
from typing import Dict, Any
from src.graph import AgentState, Node


class MacdStrategy(Node):
    def __call__(self, state: AgentState) -> Dict[str, Any]:
        data = state['data']
        data['name'] = "MacdStrategy"
        return state
