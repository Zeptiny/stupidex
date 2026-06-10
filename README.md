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
    main.py         # app entry point
    main.tcss       # styles
    llm/
      handle_input.py   # LLM streaming logic
```


# TODO - In priority order
- Thinking collapse
- Sessions
  - Implemented-ish
    - Still needs to save on disk
- Provider selector
- Implement tool calls, there already is some specs defined for tool calls and responses in message.py
- MCP (Configurable in a settings.json)
- Subagents (Configurable)
- Not re-render the full history on each update
- Default selected model (Last one selected, else first) - preserver between sessions / app close
- Move to Textual Reactive

# Needs fix
- Input messages are not queued and can have multiple concurrent connections
- Minimax M3 do not render response (Sometimes?) - needs triage

# Needs improvement
- Model selector only works with openai compatible endpoints
  - Deferred until provider selector