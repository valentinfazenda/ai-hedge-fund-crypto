import importlib
from langgraph.graph.state import CompiledGraph
from langchain_core.runnables.graph import MermaidDrawMethod
from typing import Dict, Any


def import_strategy_class(strategies_path: str):
    """
    Import a class from a dotted path like 'myproject.module.MyClass'
    """
    module_path, class_name = strategies_path.rsplit('.', 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def save_graph_as_png(app: CompiledGraph, output_file_path) -> None:
    png_image = app.get_graph().draw_mermaid_png(draw_method=MermaidDrawMethod.API)
    file_path = output_file_path if len(output_file_path) > 0 else "graph.png"
    with open(file_path, "wb") as f:
        f.write(png_image)


def deep_merge_dicts(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """
     deep merge two dicts
    :param a:
    :param b:
    :return: new Dict
    """
    result = a.copy()
    for key, value in b.items():
        if key in result and isinstance(result[key], Dict) and isinstance(value, Dict):
            result[key] = deep_merge_dicts(result[key], value)
        else:
            result[key] = value
    return result
