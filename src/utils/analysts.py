"""Constants and utilities related to analysts configuration."""
from typing import Dict, Any, List, Tuple, Callable

# Define the base analyst configuration structure
# Using a dictionary that is meant to be a single source of truth
ANALYST_CONFIG: Dict[str, Dict[str, Any]] = {
    "technical_analyst_agent": {
        "display_name": "Technical Analyst Agent",
        "agent_func": None,  # Will be populated dynamically to avoid circular imports
        "order": 0,
    }
}

# Derive ANALYST_ORDER from ANALYST_CONFIG for backwards compatibility
ANALYST_ORDER: List[Tuple[str, str]] = [
    (config["display_name"], key) 
    for key, config in sorted(ANALYST_CONFIG.items(), key=lambda x: x[1]["order"])
]


def get_analyst_nodes():
    """
    Get the mapping of analyst keys to their (node_name, agent_func) tuples.
    
    Dynamically imports the agent functions to avoid circular dependencies.
    
    Returns:
        Dict[str, Tuple[str, Callable]]: Dictionary mapping analyst keys to tuples of (node_name, agent_function)
    """
    # Import here to avoid circular imports
    from src.agents.technicals import technical_analyst_agent
    
    # Update the config with the imported function
    ANALYST_CONFIG["technical_analyst_agent"]["agent_func"] = technical_analyst_agent
    
    # Return the mapping
    return {
        key: (f"{key}", config["agent_func"]) 
        for key, config in ANALYST_CONFIG.items()
    }
