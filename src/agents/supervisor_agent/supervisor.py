from langgraph_supervisor import create_supervisor
import sys
import os

# Go two directories up (parent's parent)
PARENT_PARENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../agents_config/"))
sys.path.insert(0, PARENT_PARENT_DIR)

from agents_config.supervisor_config import ORCHESTRATOR_CONFIG

def create_orchestrator_with_agents(agents):
    """Create orchestrator when agents are ready"""
    return create_supervisor(
        agents=agents,
        **ORCHESTRATOR_CONFIG
    ).compile()