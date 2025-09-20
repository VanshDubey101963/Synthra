from src.agents.coding_agent.agent import interact
from langchain_core.tools import tool

@tool
def coding_agent_tool(project_id: str, coding_task: str) -> str:
    """Handle coding and development tasks.
    
    Use this tool for:
    - Web development (Django, React, FastAPI, Flask, Vue, Angular)
    - Backend APIs and database integration
    - Frontend components and interfaces  
    - DevOps tasks (Docker, deployment, CI/CD)
    - File creation, project scaffolding
    - Command execution and environment setup
    
    Args:
        project_id: The project identifier to work on
        coding_task: Description of the coding work to perform
    """
    print(f"🔧 [CODING TOOL] Called for project: {project_id}")
    result = interact(project_id, coding_task)
    return f"Coding completed for project {project_id}: {result}"