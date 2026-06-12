# stupidex

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e . # Editable Mode, changes take effect immediately.
```

## Usage

```bash
stupidex
```

## Development

The project uses the `src` layout:

```
pyproject.toml
src/
  stupidex/
    main.py                    # entry point (3 lines)
    app.py                     # Textual App class, UI lifecycle
    main.tcss                  # styles
    utils.py                   # Utility functions
    agents/                    # Agent definitions
      manager.py               # Subagent Manager
    domain/                    # Plain Python scripts (No Textual, no Rich, Httpx) and are usable.
      message.py               # Message, MessageRole, MessageType, Usage
      session.py               # Session, SessionManager
      tool.py                  # Tool, ExecutorREsult and related classes
    llm/
      client.py                # LLM streaming logic
      models.py                # Model fetching
      dynamic_system_prompt.py # Dynamic system prompt generation
      static_system_prompt.py  # Static system prompt provider
    screens/
      session_picker.py        # session selection screen
      model_picker.py          # model selection screen
    commands/
      session_commands.py      # commands provider
    tools/
      file_manipulation.py     # Tools for file manipulation
      search.py                # Tools for file searching (Currently grep)
      exec.py                  # Executing tools (Currently command tool)
    widgets/
      message_widget.py        # Textual widgets for messages with streaming support
```


# TODO - In priority order
- Skills
- Concurrency control for file locking
- MCP 
- LSP
- Todo management tool
  - Should act more as a task tool
    - Subagents can be assigned a task at their creation, receiving that information
    - Task have states
      - open, in progress, blocked, abandoned, done, needs_review, under_review
    - Send system reminder if the agent tries to exit when not all tasks are done
      - This can also be sent to normal subagents when trying to exit without message
        - Should we even have normal subagents in this case?
    - Reviewers are dispatched
      - Spec reviewer + code quality reviewer
    - THIS WILL REQUIRE A PLANNING MODE, POSSIBLY USING A DEDICATED TOOL FOR THAT
- Provider selector
- Approval / permission system
- AGENTS.md handling
  - Also /init command for it

## Subagents
- BTW/Side agent (Ask a question without interrupting the main flow)

## Needs fix
- Input messages are not queued and can have multiple concurrent connections

## Needs improvement
- Support for Anthropic API
- Model selector does not know the capabilities of the model (Possibly by getting them from models.dev + settings file for override/unknown capabilities?)
- Session saving to disk
- Bug: Automatically scrolling down after a message is finished
- Multiple main agent types (General, plan, etc.) that can be switched during the conversation
- Fuzzy matching on edit tool
- Resolve supplied path in tool to avoid modifing/reading files out of the workspace
  - But this could still be avoided via commands, however, with permission system and the user approving all commands then its on the user
- Bug: Something may be blocking/non parallel, when multiple subagents are spawned the CPU only uses one core
- Bug: Long thinking may eat CPU when uncollapsed
- Bug: "Offset 1 out of range"- Possibly when reading files without content

# Considerations
- Also make the read tool usable with directories?
- Remove the list_subagents tool?

# Some ground rules
- Absolute imports only
- Domain driven structure