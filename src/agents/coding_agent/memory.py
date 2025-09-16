from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph.message import add_messages
import os
from typing import TypedDict, Annotated, List, Dict 
import sqlite3

class ProjectState(TypedDict):
    messages: Annotated[List , add_messages]
    frameworks: Dict[str, str]
    files: List[str]
    tasks: List[str]
    closed: bool

DB_PATH = os.path.join(os.path.dirname(__file__) , "agent_state.sqlite")
SQLITE_CON = sqlite3.connect(DB_PATH)

checkpoint = SqliteSaver(conn=SQLITE_CON)