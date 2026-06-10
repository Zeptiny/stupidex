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
      search.py                # Tools for file searching (Currently grep)
    widgets/
      message_widget.py        # Textual widgets for messages with streaming support
```


# TODO - In priority order
- Thinking collapse
- Tool result collapse
- Provider selector
- Subagents
- Configuration file
- MCP 

## Needs fix
- Input messages are not queued and can have multiple concurrent connections
- Minimax M3 do not render response (Sometimes?) - needs triage

## Needs improvement
- Model selector only works with openai compatible endpoints
  - Deferred until provider selector
- Model selector does not know the capabilities of the model (Possibly by getting them from models.dev + settings file for override/unknown capabilities?)
- Session saving to disk
- Default selected model (Last one selected, else first) - preserve between sessions / app close
- Make IGNORED_DIRS configurable
- Context and usage only being updated when the agent finishes it response
- Bug: Automatically scrolling down after a message is finished
- Bug: Both TOOL_CALL and TOOL_RESPONSE widgets are shown after it is responded
  - Have a default message for each tool (Such as "Reading...") to be used and then delete/replace the call with the response

# Some ground rules
- Absolute imports only