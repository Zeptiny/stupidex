from stupidex.domain.agent import Agent

explorer = Agent(
    name="explorer",
    description="Explores and searches a codebase. Use when you need to find files, understand structure, or gather information without making changes.",
    system_prompt="You are an exploration agent. Your job is to search, read, and understand a codebase. "
    "Do not make any changes, only gather information. "
    "Use directory listing, file reading, glob, and grep to find what's relevant. "
    "Return a clear, concise summary of your findings.",
    available_tools=["read", "read_directory", "glob", "grep"],
)

implementer = Agent(
    name="implementer",
    description="Writes and edits code. Use when you need to implement features, fix bugs, or make code changes.",
    system_prompt="You are an implementation agent. Your job is to write and edit code. "
    "Follow existing code conventions, patterns, and standards in the codebase. "
    "Always explore the codebase first to understand context before making changes. "
    "Make modular, maintainable code.",
    available_tools=["read", "read_directory", "glob",
                     "grep", "edit", "write", "execute_command"],
)

reviewer = Agent(
    name="reviewer",
    description="Reviews code for bugs, style issues, and improvements. Use when you need a second opinion or code audit without making changes.",
    system_prompt="You are a code review agent. Your job is to review code for bugs, "
    "logic errors, style issues, and potential improvements. "
    "Read the relevant files, analyze them, and return a structured review with specific findings. "
    "Do not make any changes, only report issues.",
    available_tools=["read", "read_directory", "glob", "grep"],
)

AGENT_REGISTRY: dict[str, Agent] = {
    "explorer": explorer,
    "implementer": implementer,
    "reviewer": reviewer,
}
