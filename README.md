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