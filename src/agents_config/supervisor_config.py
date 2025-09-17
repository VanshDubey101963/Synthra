import sys
import os

from src.prompts.supervisor_prompt import SUPERVISOR_PROMPT, SAFETY_INSTRUCTIONS

ORCHESTRATOR_CONFIG = {
    "model": '',
    "prompt": SUPERVISOR_PROMPT + SAFETY_INSTRUCTIONS,
}