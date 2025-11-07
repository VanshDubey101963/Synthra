from langchain_core.messages.utils import trim_messages,count_tokens_approximately
from sqlite3 import connect as sqlite_connect
from typing import List, Annotated, Dict, Any
from langgraph.graph.message import add_messages, BaseMessage
from langgraph.prebuilt.chat_agent_executor import AgentState
from langgraph.checkpoint.sqlite import SqliteSaver

def pre_model_hook(state):
    trimmed_messages = trim_messages(
        state["messages"],
        strategy="last",
        token_counter=count_tokens_approximately,
        max_tokens=10000,
        start_on="human",
        include_system=True,
        end_on=("human", "tool"),
    )
    return {"messages": trimmed_messages}

class ProjectStateSchema(AgentState):
    messages: Annotated[List[BaseMessage], add_messages] # type: ignore[override]
    files: List[str]
    remaining_steps: int # type: ignore[override]
    context: Dict[str, Any]


sqlite_connection = sqlite_connect(
    database="agent_memory.sqlite", check_same_thread=False
)
checkpointer = SqliteSaver(sqlite_connection)
