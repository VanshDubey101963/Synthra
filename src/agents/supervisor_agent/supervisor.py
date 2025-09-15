from langgraph_supervisor import create_supervisor
from ..agents_config.supervisor_config import ORCHESTRATOR_CONFIG

def create_orchestrator_with_agents(agents):
    """Create orchestrator when agents are ready"""
    return create_supervisor(
        agents=agents,
        **ORCHESTRATOR_CONFIG
    ).compile()