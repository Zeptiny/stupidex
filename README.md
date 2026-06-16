# stupidex

## TODO do Trabalho Final
- [x] Ao menos 2 agentes com papéis distintos e justificados
  - Temos 25 agentes pré definidos (4 core + 10 reviewers + 5 doc-review + 3 researchers + 2 specialized + 1 PR resolver)
- [x] LLM integrado - tomada de decisão, geração ou roteamento
  - O projeto necessita de LLM para ser útil, com o principal tomando deciões e roteamento (Subagentes) e geração com principal ou subagentes (Código, exploração, etc.)
- [x] Modelo local (Ollama) - não apenas API paga
  - Ele funciona com modelos locais desde que foneçam API compatível com OpenAI (Anthropic planejada)
- [ ] MCP com ao menos 1 tool e 1 resource implementados
- [x] Pipeline RAG: ingestão -> Embedding -> busca -> resposta
- [x] Vector store (ChromeDB/FAISS) com embedding reais
- [x] Mínimo 3 tools disponíveis e funcionais para os agentes
  - O projeto conta com 19 tools configuráveis por agente
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
allowed_tools:
  - read
  - edit
  - execute_command
allowed_skills:
  - '*'
---

System prompt content here...
```

**Required fields:** `name`, `type`, `tier`, `description`, `allowed_tools`.
**Optional fields:** `allowed_skills` (defaults to `[]` — no skill access).

**`allowed_skills` patterns:**
- `*` — matches all skills
- `work*` — matches skills starting with `work`
- `code-review` — matches exact name
- Multiple patterns are unioned: `["work", "debug"]` matches both

**Built-in agents:**

Core:
| Agent | Type | Tier | Description |
|-------|------|------|-------------|
| `general` | internal | papudo | Main agent, handles direct conversation |
| `explorer` | subagent | tolo | Read-only codebase exploration |
| `implementer` | subagent | papudo | Writes and edits code |
| `reviewer` | subagent | papaca | Code review for bugs and improvements |

Specialized reviewers (used by `code-review` skill):
| Agent | Type | Tier | Description |
|-------|------|------|-------------|
| `correctness-reviewer` | subagent | papaca | Reviews code for logic errors, edge cases, state management bugs |
| `security-reviewer` | subagent | papaca | Reviews for exploitable vulnerabilities, input validation, auth issues |
| `performance-reviewer` | subagent | papaca | Reviews for bottlenecks, N+1 queries, memory usage, scalability |
| `maintainability-reviewer` | subagent | papudo | Reviews for premature abstraction, dead code, coupling, naming |
| `testing-reviewer` | subagent | papudo | Reviews for test coverage gaps, weak assertions, brittle tests |
| `adversarial-reviewer` | subagent | papaca | Constructs failure scenarios to break the implementation |
| `reliability-reviewer` | subagent | papaca | Reviews error handling, retries, circuit breakers, timeouts |
| `api-contract-reviewer` | subagent | papudo | Reviews API routes, request/response types, serialization |
| `data-integrity-guardian` | subagent | papaca | Reviews migrations, data models, persistent data for safety |
| `code-simplicity-reviewer` | subagent | papudo | Final pass for YAGNI violations and simplification opportunities |

Research and analysis agents:
| Agent | Type | Tier | Description |
|-------|------|------|-------------|
| `learnings-researcher` | subagent | tainha | Searches docs/solutions/ for applicable past learnings |
| `web-researcher` | subagent | tainha | Codebase research via RAG search and semantic analysis |
| `architecture-strategist` | subagent | papaca | Analyzes code changes for pattern compliance and design integrity |
| `agent-native-reviewer` | subagent | papaca | Reviews for agent-native parity (every user action = agent tool) |
| `spec-flow-analyzer` | subagent | papudo | Analyzes specs for user flow completeness and gap identification |

Document review agents (used by `doc-review` skill):
| Agent | Type | Tier | Description |
|-------|------|------|-------------|
| `adversarial-document-reviewer` | subagent | papaca | Challenges premises, surfaces unstated assumptions in docs |
| `coherence-reviewer` | subagent | papudo | Reviews docs for internal consistency and contradictions |
| `feasibility-reviewer` | subagent | papudo | Evaluates whether proposed approaches will survive reality |
| `product-lens-reviewer` | subagent | papaca | Reviews docs as a senior product leader |
| `scope-guardian-reviewer` | subagent | papudo | Reviews for scope alignment and unjustified complexity |
| `pr-comment-resolver` | subagent | papudo | Evaluates and resolves PR review threads |

### Agent Tiers

Tiers control the intelligence/speed tradeoff for each agent. Lower tiers use faster, cheaper models; higher tiers use more capable models for complex reasoning.

| Tier | Intelligence | Speed | Expected Use Cases |
|------|--------------|-------|-------------------|
| `tolo` | Low | Very Fast | Simple, mechanical tasks: file listing, basic searches, reading files, glob matching. No complex reasoning needed. |
| `tainha` | Medium | Fast | Code exploration, grep analysis, understanding file structure, reading comprehension, summarizing findings. |
| `papudo` | High | Standard | Implementation tasks, writing code, refactoring, multi-file changes, bug fixes, following code conventions. |
| `papaca` | Very High | Slower | Architecture decisions, complex debugging, code review, design analysis, evaluating trade-offs, careful judgment. |

Map tiers to models in `~/.stupidex/config.json` under `tier_models`. Assign cheaper models to low tiers and more capable models to high tiers to optimize cost and latency.

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

Core workflow:
| Skill | Description | When to use |
|-------|-------------|-------------|
| `strategy` | Create/maintain STRATEGY.md (product direction) | "write our strategy", "what are we working on" |
| `ideate` | Generate and critically evaluate grounded ideas | "give me ideas", "what should I improve", "surprise me" |
| `brainstorm` | Explore requirements through dialogue, write requirements doc | "let's brainstorm", "what should we build", vague requests |
| `doc-review` | Review requirements/plan docs with parallel persona agents | "review this doc", "improve this requirements doc" |
| `plan` | Create structured implementation plans | "plan this", "how should we build", "break this down" |
| `work` | Execute plans efficiently with incremental commits | "implement this", "build it", "execute the plan" |
| `debug` | Find root causes and fix bugs systematically | "debug this", "why is this failing", "fix this bug" |
| `code-review` | Structured review with tiered persona agents | "review this", before creating a PR |
| `resolve-pr-feedback` | Evaluate and fix PR review feedback | "resolve PR feedback", "address review comments" |
| `commit` | Create git commits with clear messages | "commit this", "save my changes" |
| `commit-push-pr` | Commit, push, and open a PR | "ship this", "create a PR", "commit and PR" |
| `compound` | Document solved problems to compound knowledge | "document this", "what did we learn", after fixing a bug |
| `compound-refresh` | Refresh stale docs in docs/solutions/ | "refresh my learnings", "audit docs/solutions/" |
| `simplify-code` | Refactor for clarity, reuse, and efficiency | "simplify this", "clean up", "refactor for clarity" |
| `lfg` | Full autonomous pipeline (plan → work → review → commit → PR → CI watch) | "ship this end-to-end", "do everything", hands-off execution |

## Workflow

Skills chain into a compound engineering pipeline. Each step builds on the previous:

```
strategy → ideate → brainstorm → [doc-review] → plan → work → [debug] → code-review → [resolve-pr-feedback] → commit-push-pr → compound
```

### Typical flows

**Feature development:**
```
brainstorm → plan → work → code-review → commit-push-pr → compound
```

**Bug fix:**
```
debug → (fix) → code-review → compound
```

**Code review:**
```
code-review → resolve-pr-feedback → compound
```

**Full autonomous pipeline (`lfg`):**
```
plan → work → code-review → fix → test → commit-push-pr
```

### Knowledge Management

The compounding system documents solved problems so future work avoids re-discovering known solutions:

- **`docs/solutions/`** — Structured learnings with YAML frontmatter, organized by category:
  - `developer-experience/` — Dev setup, CI, tooling issues
  - `integrations/` — Cross-platform bugs, target compatibility
  - `workflow/` — Skill/agent design patterns, process improvements
  - `skill-design/` — Plugin architecture patterns
- **`CONCEPTS.md`** — Shared domain vocabulary that grounds all agents in the project's language
- **`learnings-researcher` agent** — Searches docs/solutions/ before implementation to surface prior knowledge
- **`compound` skill** — Documents new solutions after they're solved
- **`compound-refresh` skill** — Audits and maintains existing learnings over time

### Agent Delegation Pattern

The general agent delegates specialized work to subagents:

1. **Research** — `explorer`, `learnings-researcher`, `web-researcher` gather context
2. **Implementation** — `implementer` writes code guided by plans
3. **Review** — `code-review` skill spawns parallel reviewer personas (correctness, security, performance, etc.)
4. **Resolution** — `pr-comment-resolver` addresses feedback
5. **Documentation** — `compound` skill captures the learning

Each agent only has access to its `allowed_tools` and `allowed_skills`, enforcing separation of concerns.

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
| `rag_search` | Semantic code search |
| `rag_index` | Index status, reindex, clear |
| `todo_create` | Create a task |
| `todo_update` | Update task status/details |
| `todo_list` | List tasks filtered by status |
| `todo_delete` | Delete a task |

## RAG (Retrieval-Augmented Generation)

The project includes a built-in RAG pipeline for code-aware semantic search. It indexes your project, chunks files by language-aware rules, embeds them, and stores vectors locally using numpy + SQLite.

### Quick Start

```bash
# Index the current project
# In the command palette (Ctrl+P): /index
```

The agents will use the rag tool ad needed

### Embedding Providers

Two embedding backends are supported:

| Provider | How it works | Requires |
|----------|-------------|----------|
| `fastembed` (default) | Runs quantized models locally via ONNX Runtime | Included by default |
| `openai` | Calls OpenAI-compatible API (local or remote) | `litellm`, API key |

#### Using fastembed (default, local)

fastembed is included by default — no extra install needed. The default model (`BAAI/bge-small-en-v1.5`, ~77 MB) is auto-downloaded on first use. No API key needed — fully offline.

To use a different model, configure in `~/.stupidex/config.json`:

```json
{
  "rag_embedding_model": "BAAI/bge-base-en-v1.5"
}
```

Or via environment variables:

```bash
STUPIDEX_RAG_EMBEDDING_MODEL="BAAI/bge-base-en-v1.5" stupidex
```

**Available fastembed models:**

| Model | Dims | Size | Best for |
|-------|------|------|----------|
| `BAAI/bge-small-en-v1.5` (default) | 384 | ~77 MB | Fast, good quality |
| `BAAI/bge-base-en-v1.5` | 768 | ~430 MB | Better quality |
| `sentence-transformers/all-MiniLM-L6-v2` | 384 | ~80 MB | General purpose |
| `nomic-ai/nomic-embed-text-v1.5-Q` | 768 | ~550 MB | Multilingual |

#### Using OpenAI-compatible APIs

Works with any OpenAI-compatible endpoint — OpenAI, Ollama, vLLM, etc.

```bash
OPENAI_API_KEY="your-key" stupidex
```

Or in `~/.stupidex/config.json`:

```json
{
  "rag_embedding_provider": "openai",
  "base_url": "http://localhost:11434/v1",
  "rag_embedding_model": "nomic-embed-text"
}
```

### RAG Configuration

All RAG settings in `~/.stupidex/config.json`:

```json
{
  "rag_embedding_provider": "fastembed",
  "rag_embedding_model": "BAAI/bge-small-en-v1.5",
  "rag_chunk_size": 2000,
  "rag_chunk_overlap": 200,
  "rag_top_k": 5,
  "rag_max_file_size": 512000
}
```

| Field | Default | Description |
|-------|---------|-------------|
| `rag_embedding_provider` | `"fastembed"` | `"fastembed"` (local) or `"openai"` (API) |
| `rag_embedding_model` | `""` | Model name (provider-specific default if empty) |
| `rag_chunk_size` | `2000` | Max characters per chunk |
| `rag_chunk_overlap` | `200` | Overlap between consecutive chunks |
| `rag_top_k` | `5` | Number of results to return |
| `rag_max_file_size` | `512000` | Skip files larger than this (bytes) |

Environment variable overrides: `STUPIDEX_RAG_EMBEDDING_PROVIDER`, `STUPIDEX_RAG_EMBEDDING_MODEL`, `STUPIDEX_RAG_CHUNK_SIZE`, `STUPIDEX_RAG_CHUNK_OVERLAP`, `STUPIDEX_RAG_TOP_K`, `STUPIDEX_RAG_MAX_FILE_SIZE`.

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
      rag.py                   # RAG index/search tool
    rag/                       # RAG pipeline
      chunker.py               # Language-aware file chunking
      embedder.py              # Embedding provider abstraction
      indexer.py               # Project indexing orchestrator
      store.py                 # SQLite + numpy vector store
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
  },
  "rag_embedding_provider": "fastembed",
  "rag_embedding_model": "BAAI/bge-small-en-v1.5"
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
- Provider selector
- Approval / permission system
- AGENTS.md handling
  - Also /init command for it
- Session saving to disk
- Web fetch tool or MCP
- ask_question tool

## Subagents
- BTW/Side agent (Ask a question without interrupting the main flow)

## Needs improvement
- Support for Anthropic API
- Model selector does not know the capabilities of the model (Possibly by getting them from models.dev + settings file for override/unknown capabilities?)
- Bug: Automatically scrolling down after a message is finished
- Multiple main agent types (General, plan, etc.) that can be switched during the conversation
- Fuzzy matching on edit tool
- Resolve supplied path in tool to avoid modifying/reading files out of the workspace
  - But this could still be avoided via commands, however, with permission system and the user approving all commands then its on the user
- Bug: Something may be blocking/non parallel, when multiple subagents are spawned the CPU only uses one core
- Message queue for the user

# Considerations
- Make the read tool usable with directories?
- Remove the list_subagents tool?
- Remove the list_skills tool?

# Some ground rules
- Absolute imports only
- Domain driven structure
- Follow ruff linting (Please)
