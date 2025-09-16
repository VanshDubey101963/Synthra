import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "../")

from prompts.supervisor_prompt import SUPERVISOR_PROMPT, SAFETY_INSTRUCTIONS

ORCHESTRATOR_CONFIG = {
    "model": '',
    "prompt": SUPERVISOR_PROMPT + SAFETY_INSTRUCTIONS,
}