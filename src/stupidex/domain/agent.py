from dataclasses import dataclass
from enum import Enum


class AgentTypes(Enum):
    INTERNAL = "Internal"  # General, Plan, etc.
    HIDDEN = "Hidden"  # Compactor, etc.
    SUBAGENT = "Subagent"  # Explorer, Review, etc.


@dataclass
class Agent:
    name: str
    type: AgentTypes
    description: str
    system_prompt: str
    available_tools: list[str]
