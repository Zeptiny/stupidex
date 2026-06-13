# stupidex

## TODO do Trabalho Final
- [x] Ao menos 2 agentes com papéis distintos e justificados
  - Temos 4 agentes pré definidos que podem ser chamados pelo agente principal
- [x] LLM integrado - tomada de decisão, geração ou roteamento
  - O projeto necessita de LLM para ser útil, com o principal tomando deciões e roteamento (Subagentes) e geração com principal ou subagentes (Código, exploração, etc.)
- [x] Modelo local (Ollama) - não apenas API paga
  - Ele funciona com modelos locais desde que foneçam API compatível com OpenAI (Anthropic planejada)
- [ ] MCP com ao menos 1 tool e 1 resource implementados
- [ ] Pipeline RAG: ingestão -> Embedding -> busca -> resposta
- [ ] Vector store (ChromeDB/FAISS) com embedding reais
- [x] Mínimo 3 tools disponíveis e funcionais para os agentes
  - O projeto conta com 13 tools configuráveis por agente
- [x] Interface CLI testável - fluxo demonstrável em terminal
  - A interface é feita com Textual e o usuário tem acesso a todo o fluxo de todos os agentes
- [x] Repositório GiHub público com código completo
  - Você está vendo agora
- [ ] README com todos os elementos exigidos no enunciado


## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e . # Editable Mode, changes take effect immediately.
```

Configure the default models and API route on `~/.stupidex/config.json`

## Usage

```bash
stupidex
```

If you are using a third party provider you need to pass the API KEY via environment variables

```bash
OPENAI_API_KEY="your key" stupidex
```

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+P` | Open command palette |
| `Ctrl+S` | Submit input |
| `Ctrl+C` | Clear input |
| `Ctrl+B` | Toggle focus between input and sidebar |
| `Escape` | Interrupt agent / subagents |
| `↑` / `↓` | Navigate sidebar entries (when sidebar is focused) |
| `Enter` / `Space` | Activate sidebar entry or toggle collapsible section |

## Agents

Agents are defined as markdown files with YAML frontmatter. On first run, default agents are seeded to `~/.stupidex/agents/`.

**Location:**
- Home: `~/.stupidex/agents/<name>/AGENT.md`
- Project: `.stupidex/agents/<name>/AGENT.md` (overrides home)

**Format:**
```markdown
---
name: my-agent
type: subagent
tier: papudo
description: What this agent does
available_tools:
  - read
  - edit
  - execute_command
---

System prompt content here...
```

**Built-in agents:**
| Agent | Type | Tier | Description |
|-------|------|------|-------------|
| `general` | internal | papudo | Main agent, handles direct conversation |
| `explorer` | subagent | tolo | Read-only codebase exploration |
| `implementer` | subagent | papudo | Writes and edits code |
| `reviewer` | subagent | papaca | Code review for bugs and improvements |

## Skills

Skills are reusable workflow templates that guide the agent through complex tasks. Defined as markdown files with YAML frontmatter.

**Location:**
- Home: `~/.stupidex/skills/<name>/SKILL.md`
- Project: `.stupidex/skills/<name>/SKILL.md` (overrides home)

**Format:**
```markdown
---
name: my-skill
description: What this skill does and when to use it
---

Skill instructions here...
```

**Built-in skills:**
| Skill | Description | When to use |
|-------|-------------|-------------|
| `brainstorm` | Explore requirements through dialogue | "let's brainstorm", vague feature requests |
| `plan` | Create structured implementation plans | "plan this", "how should we build" |
| `work` | Execute plans efficiently | "implement this", "build it" |
| `debug` | Find root causes and fix bugs | "debug this", "why is this failing" |
| `commit` | Create git commits | "commit this", "save my changes" |
| `simplify-code` | Refactor for clarity | "simplify this", "clean up" |
| `code-review` | Review code for issues | "review this", before merging |

## Tools

Available tools for agents:

| Tool | Description |
|------|-------------|
| `read` | Read file contents |
| `read_directory` | List directory contents |
| `glob` | Find files by pattern |
| `grep` | Search file contents |
| `edit` | Edit files |
| `write` | Write files |
| `execute_command` | Run shell commands |
| `delegate_to_subagent` | Spawn a subagent |
| `wait_for_subagent` | Wait for subagent results |
| `list_subagents` | List active subagents |
| `interrupt_subagents` | Cancel running subagents |
| `skill` | Load a skill |
| `list_skills` | List available skills |

## Linting

The project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting.
Configuration is in `pyproject.toml`:

- **Target**: Python 3.11
- **Line length**: 120
- **Rules**: `E`, `F`, `I`, `N`, `W`, `UP`, `B`, `SIM` (with `E501` and `SIM105` ignored)

Run locally:

```bash
ruff check src/        # lint
ruff check src/ --fix  # auto-fix
```

Linting runs automatically on push/PR to `main` via GitHub Actions (`.github/workflows/lint.yml`).

**VSCode**: Install the [Ruff extension](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff), the `.vscode/settings.json` is already configured for format-on-save and auto-fix on save.

## Development

The project uses the `src` layout:

```
pyproject.toml
src/
  stupidex/
    main.py                    # entry point
    app.py                     # Textual App class, UI lifecycle
    main.tcss                  # styles
    utils.py                   # Shared utilities (frontmatter parsing, directory tree)
    agents/                    # Agent system
      __init__.py              # Agent registry and loading
      manager.py               # Subagent Manager
      defaults/                # Default agent definitions
    skills/                    # Skill system
      __init__.py              # Skill registry and loading
      defaults/                # Default skill definitions
    domain/                    # Core domain models
      message.py               # Message, MessageRole, MessageType, Usage
      session.py               # Session, SessionManager
      tool.py                  # Tool, ExecutorResult
      agent.py                 # Agent, AgentTypes, ModelTier
      skill.py                 # Skill
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
    tools/                     # Tool implementations
      file_manipulation.py     # read, write, edit, glob, read_directory
      search.py                # grep
      exec.py                  # execute_command
      subagent.py              # subagent management tools
      skill.py                 # skill and list_skills tools
    widgets/
      message_widget.py        # Textual widgets for messages
      sidebar.py               # Right sidebar
```

## Configuration

**Location:** `~/.stupidex/config.json`

```json
{
  "base_url": "https://opencode.ai/zen/go/v1",
  "default_model": "mimo-v2.5",
  "tier_models": {
    "tolo": "mimo-v2.5",
    "tainha": "mimo-v2.5",
    "papudo": "mimo-v2.5",
    "papaca": "mimo-v2.5"
  }
}
```

Project-level config: `.stupidex.json` (overrides home config).

## TODO - In priority order
- Sandboxing for shell command execution, file operations, and project-level config/agent/skill overrides
  - Arbitrary shell command execution with no sandboxing or allowlist (exec.py)
  - Unrestricted file read/write/edit to arbitrary paths including sensitive system files (file_manipulation.py)
  - 24 bare `except Exception` blocks that silently swallow errors across app.py
  - `write` tool creates arbitrary directory trees with `mkdir(parents=True)` (file_manipulation.py)
  - Error messages leak command strings and file paths in tool execution errors (exec.py)
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

## Needs improvement
- Support for Anthropic API
- Model selector does not know the capabilities of the model (Possibly by getting them from models.dev + settings file for override/unknown capabilities?)
- Session saving to disk
- Bug: Automatically scrolling down after a message is finished
- Multiple main agent types (General, plan, etc.) that can be switched during the conversation
- Fuzzy matching on edit tool
- Resolve supplied path in tool to avoid modifying/reading files out of the workspace
  - But this could still be avoided via commands, however, with permission system and the user approving all commands then its on the user
- Bug: Something may be blocking/non parallel, when multiple subagents are spawned the CPU only uses one core
- Bug: "Offset 1 out of range"- Possibly when reading files without content
- Message queue for the user
- Limit available skills per subagent

# Considerations
- Make the read tool usable with directories?
- Remove the list_subagents tool?
- Remove the list_skills tool?

# Some ground rules
- Absolute imports only
- Domain driven structure
- Follow ruff linting (Please)
