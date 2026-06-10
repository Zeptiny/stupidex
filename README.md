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
    widgets/
      message_display.py       # Rich rendering for messages
```


# TODO - In priority order
- Thinking collapse
- Tool result collapse
- Provider selector
- Implement tool calls, there already is some specs defined for tool calls and responses in message.py
  - Subagents (Configurable)
- Configuration file
- MCP 

## Needs fix
- Input messages are not queued and can have multiple concurrent connections
- Minimax M3 do not render response (Sometimes?) - needs triage
- Not re-render the full history on each update

## Needs improvement
- Model selector only works with openai compatible endpoints
  - Deferred until provider selector
- Model selector does not know the capabilities of the model (Possibly by getting them from models.dev + settings file for override/unknown capabilities?)
- Session saving to disk
- Default selected model (Last one selected, else first) - preserver between sessions / app close
- Make IGNORED_DIRS configurable

# Some ground rules
- Absolute imports only