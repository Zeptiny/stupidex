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
- Commands
- Sessions
  - Implemented-ish
    - Resuming not possible
- Model selector
- Provider selector
- Implement tool calls, there already is some specs defined for tool calls and responses in message.py
- MCP (Configurable in a settings.json)
- Subagents (Configurable)
- Not re-render the full history on each update

# Needs fix
- Input messages are not queued and can have multiple concurrent connections