from typing import Annotated
from src.agents.coding_agent.agent import coding_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

@tool
def delegate_to_coding_agent(
    task_description: Annotated[str, "Exact task that coding agent needs to do"], 
    project_id: Annotated[str, "Exact project_id to use for saving context as well as project directory name"]
):
    
    """
        This tool hands off coding tasks to the coding agent
        
        Args:
            task_description: str
            project_id: str
            
        returns a str 
    """
    
    prompt = f"""
        For project_id {project_id},
        {task_description}
    """
    
    config = {"configurable": {"thread_id": project_id}, "recursion_limit": 100}
    messages = [
        HumanMessage(content=prompt)
    ]
    
    
    for mode, chunk in coding_agent.stream(
        {"messages": messages},
        config=config,
        stream_mode=["messages", "updates"]
    ):
        if mode == "messages":
            message_chunk, metadata = chunk
            if hasattr(message_chunk, "content") and message_chunk.content:
                print(message_chunk.content, end="\n")
                
    print(coding_agent.get_state(project_id))

    return "✅ All Tasks Done!!"
                