from langgraph.prebuilt import create_react_agent
from src.agents.supervisor_agent.tool import coding_agent_tool
from langchain_core.messages import SystemMessage,HumanMessage
from src.model.model import get_llm

llm = get_llm()

supervisor_agent = create_react_agent(
    model=llm,
    tools=[coding_agent_tool],    
)

def supervisor_interaction(user_input: str) -> str:
    """Supervisor agent that decides which agent tool to use."""
    
    print(f"🎯 [SUPERVISOR] Processing: {user_input}")
    print("-" * 50)
    
    config = {"configurable": {"thread_id": "supervisor_main"}}
    
    messages = [
        SystemMessage(content=(
            "You are an intelligent supervisor agent that delegates tasks to specialized tools\n\n"
            "Whatever prompt user provides just give it to the tool along with whatever the tool requires\n"
            "AVAILABLE AGENT TOOLS:\n"
            "🔧 coding_agent_tool: For all coding, web development, APIs, databases, file creation\n"
            "🔍 research_agent_tool: For research, documentation, technology comparisons\n"  
        )),
        HumanMessage(content=user_input)
    ]
    
    print("🤔 [SUPERVISOR] Deciding which agent to use...")
    
    for mode, chunk in supervisor_agent.stream(
        {"messages": messages},
        config=config,
        stream_mode=["messages", "updates"]
    ):
        if mode == "messages":
            message_chunk, metadata = chunk
            if hasattr(message_chunk, "content") and message_chunk.content:
                # Print supervisor's reasoning (optional)
                print(f"🧠 [SUPERVISOR]: {message_chunk.content}")
    
    print("✅ [SUPERVISOR] Task delegation completed")
    return "✅ Supervisor task completed"