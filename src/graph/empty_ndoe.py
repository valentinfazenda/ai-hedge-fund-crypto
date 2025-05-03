"""
Merged data node.
"""
from typing import Dict, Any
from .node import Node, AgentState


class EmptyNode(Node):
    def __call__(self, state: AgentState) -> Dict[str, Any]:
        """
        EmptyNode
        """
        return state
