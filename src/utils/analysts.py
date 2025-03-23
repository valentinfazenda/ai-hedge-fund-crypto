"""Constants and utilities related to analysts configuration."""
from src.agents.technicals import technical_analyst_agent


# Define analyst configuration - single source of truth
# you can add your agents here.
ANALYST_CONFIG = {
    "technical_analyst_agent": {
        "display_name": "Technical Analyst Agent",
        "agent_func": technical_analyst_agent,
        "order": 0,
    }
}

# Derive ANALYST_ORDER from ANALYST_CONFIG for backwards compatibility
ANALYST_ORDER = [(config["display_name"], key) for key, config in sorted(ANALYST_CONFIG.items(), key=lambda x: x[1]["order"])]


def get_analyst_nodes():
    """Get the mapping of analyst keys to their (node_name, agent_func) tuples."""
    return {key: (f"{key}", config["agent_func"]) for key, config in ANALYST_CONFIG.items()}
