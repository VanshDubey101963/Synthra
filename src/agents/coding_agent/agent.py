
from langchain_core.messages import HumanMessage, SystemMessage
from local_llm.llm import get_llm
from langgraph.prebuilt import create_react_agent
from src.agents.coding_agent.tool import tools
from src.agents.coding_agent.memory import ProjectState , checkpoint

llm = get_llm()

def interact(project_id: str, user_input: str) -> str:
    """Interact with the multi-framework coding agent.
    
    Args:
        project_id: Unique identifier for the project thread
        user_input: User's message/instruction
    
    Returns:
        str: Agent's response
    """
    agent = create_react_agent(
        model=llm,
        tools=tools,
        checkpointer=checkpoint,
        state_schema=ProjectState
    )

    config = {"configurable": {"thread_id": project_id}, "recursion_limit": 50}

    messages = [
        SystemMessage(content=(
            "You are a coding agent working on PROJECT: '{project_id}'. "
            "You support multiple frameworks for backend and frontend. "
            "IMPORTANT: When using tools, always pass the project_id parameter as the first argument. "
            f"The current project_id is: '{project_id}'. "
            "When you start a project, decide or ask which frameworks will be used (backend, frontend). "
            "Use `write_files` tool to scaffold files. Use `run_shell` for runtime commands. "
            "For modifications, inspect existing files via `list_files` or reading file content, then update via `write_files`. "
            "Use each framework's commands appropriately for dependencies, build, etc. "
            "Project remains active until user says 'Project is over'. "
            "For projects try to create virtual environments before installing packages."
            "If a project is already present with a project id then do not proceed further and just reply with project already exists only if project were to be created from scratch"
            f"Remember: ALL tool calls must include project_id='{project_id}' as the first parameter."
            f"Remember to check which operating system is currently being used"
        )),
        HumanMessage(content=f"[Project: {project_id}] {user_input}")
        ]

        # Use stream here
    for mode, chunk in agent.stream(
        {"messages": messages},
        config=config,
        stream_mode=["messages", "updates"]
    ):
        if mode == "messages":
            message_chunk, metadata = chunk
            if hasattr(message_chunk, "content") and message_chunk.content:
                print(message_chunk.content, end="\n", flush=True)

    return "✅ Done streaming response"