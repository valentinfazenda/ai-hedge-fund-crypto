from typing import List, Dict, TypedDict, Annotated, Sequence, Any
import operator
from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages
from utils.util_func import deep_merge_dicts


class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    data: Annotated[Dict[str, Any], deep_merge_dicts]
    metadata: Annotated[Dict[str, Any], deep_merge_dicts]

