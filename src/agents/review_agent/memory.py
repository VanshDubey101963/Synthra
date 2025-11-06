"""Memory and state management for the review agent."""
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph.message import add_messages
import os
from typing import TypedDict, Annotated, List, Dict, Any
import sqlite3


class ReviewState(TypedDict):
    """State schema for review agent conversations."""
    messages: Annotated[List, add_messages]
    project_path: str
    files: List[str]
    git_history: List[Dict[str, Any]]
    code_analysis: Dict[str, Any]
    project_analysis: Dict[str, Any]
    remaining_steps: int
    closed: bool


# Database path for persistent state
DB_PATH = os.path.join(os.path.dirname(__file__), "review_agent_state.db")
SQLITE_CON = sqlite3.connect(DB_PATH, check_same_thread=False)

# Checkpoint saver for conversation persistence
checkpoint = SqliteSaver(conn=SQLITE_CON)
