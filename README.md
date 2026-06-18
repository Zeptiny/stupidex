# stupidex

## TODO do Trabalho Final
- [x] Ao menos 2 agentes com papéis distintos e justificados
  - Temos 25 agentes pré definidos (4 core + 10 reviewers + 5 doc-review + 3 researchers + 2 specialized + 1 PR resolver)
- [x] LLM integrado - tomada de decisão, geração ou roteamento
  - O projeto necessita de LLM para ser útil, com o principal tomando deciões e roteamento (Subagentes) e geração com principal ou subagentes (Código, exploração, etc.)
- [x] Modelo local (Ollama) - não apenas API paga
  - Ele funciona com modelos locais desde que foneçam API compatível com OpenAI (Anthropic planejada)
- [x] MCP com ao menos 1 tool e 1 resource implementados
  - MCP client com suporte a stdio e HTTP/SSE, Context7 incluso como padrão
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

Configure providers, models, and API keys in `~/.stupidex/config.json`. See the [Providers](#providers) section for examples.

## Usage

```bash
stupidex
```

If your provider doesn't ship an API key in config, set the environment variable litellm expects (e.g. `OPENAI_API_KEY`):

```bash
OPENAI_API_KEY="your key" stupidex
```

Per-provider keys can also be configured inline or via a named env var — see [Providers](#providers).

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
| `get_file_skeleton` | Structural outline of a file (definitions only) |
| `get_function` | Extract specific function with imports and class context |
| `find_symbol_references` | Find all definitions and references for a symbol name |
| `replace_symbol` | Replace an entire symbol definition (including docstring and decorators) |
| `rename_symbol` | Rename a symbol across all files in one call |
| `todo_create` | Create a task |
| `todo_update` | Update task status/details |
| `todo_list` | List tasks filtered by status |
| `todo_delete` | Delete a task |
| `read_mcp_resource` | Read a resource from an MCP server by URI |
| `mcp_*` | Dynamically registered MCP tools (e.g., `mcp_context7_resolve-library-id`) |

## RAG (Retrieval-Augmented Generation)

The project includes a built-in RAG pipeline for code-aware semantic search. It indexes your project, chunks files by language-aware rules, embeds them, and stores vectors locally using numpy + SQLite.

### Quick Start

```bash
# Index the current project
# In the command palette (Ctrl+P): /index
```

The agents will use the rag tool ad needed

### Embedding Providers

RAG embeddings use the same `alias/model` routing as chat models. Configure a single field — `rag_embedding_model` — with either a `fastembed/<model_id>` reference (local ONNX, no network) or a `<provider-alias>/<model>` reference (routes through the providers dict to `litellm.aembedding`).

| Reference form | How it works | Requires |
|----------------|-------------|----------|
| `fastembed/<model_id>` (default) | Runs quantized models locally via ONNX Runtime | Included by default |
| `<alias>/<model>` (e.g. `work-openai/text-embedding-3-small`) | Calls the provider's embedding API via litellm | Provider configured + API key |

#### Using fastembed (default, local)

The shipping default is `fastembed/BAAI/bge-small-en-v1.5` (~77 MB, auto-downloaded on first use). No API key, no network after first run.

To use a different local model, set `rag_embedding_model` to `fastembed/<model_id>`:

```json
{
  "rag_embedding_model": "fastembed/BAAI/bge-base-en-v1.5"
}
```

Or via environment variable:

```bash
STUPIDEX_RAG_EMBEDDING_MODEL="fastembed/BAAI/bge-base-en-v1.5" stupidex
```

**Available fastembed models:**

| Model | Dims | Size | Best for |
|-------|------|------|----------|
| `BAAI/bge-small-en-v1.5` (default) | 384 | ~77 MB | Fast, good quality |
| `BAAI/bge-base-en-v1.5` | 768 | ~430 MB | Better quality |
| `sentence-transformers/all-MiniLM-L6-v2` | 384 | ~80 MB | General purpose |
| `nomic-ai/nomic-embed-text-v1.5-Q` | 768 | ~550 MB | Multilingual |

#### Using a provider-routed embedding model

Any `alias/model` reference registered in your `providers` config works. For example, with a `work-openai` provider configured (see [Providers](#providers)):

```json
{
  "rag_embedding_model": "work-openai/text-embedding-3-small"
}
```

### RAG Configuration

All RAG settings in `~/.stupidex/config.json`:

```json
{
  "rag_embedding_model": "fastembed/BAAI/bge-small-en-v1.5",
  "rag_chunk_size": 2000,
  "rag_chunk_overlap": 200,
  "rag_top_k": 5,
  "rag_max_file_size": 512000
}
```

| Field | Default | Description |
|-------|---------|-------------|
| `rag_embedding_model` | `"fastembed/BAAI/bge-small-en-v1.5"` | `alias/model` reference (supports `fastembed/<id>` for local ONNX) |
| `rag_chunk_size` | `2000` | Max characters per chunk |
| `rag_chunk_overlap` | `200` | Overlap between consecutive chunks |
| `rag_top_k` | `5` | Number of results to return |
| `rag_max_file_size` | `512000` | Skip files larger than this (bytes) |

Environment variable overrides: `STUPIDEX_RAG_EMBEDDING_MODEL`, `STUPIDEX_RAG_CHUNK_SIZE`, `STUPIDEX_RAG_CHUNK_OVERLAP`, `STUPIDEX_RAG_TOP_K`, `STUPIDEX_RAG_MAX_FILE_SIZE`.

## AST Tools

The project includes AST-aware tools for structural code operations. These tools use [tree-sitter](https://tree-sitter.github.io/) to parse source files into syntax trees, enabling precise symbol extraction, cross-file references, and code transformations that text-based tools cannot reliably perform.

### Supported Languages

v1 supports **Python**, **JavaScript**, **TypeScript**, and **TSX**. TSX reuses the TypeScript grammar and query file.

### Quick Start

```bash
# Index the project for AST symbol lookup
# In the command palette (Ctrl+P): /reindex-ast
```

Index-dependent tools (`find_symbol_references`, `rename_symbol`) trigger a full project scan on first call automatically. Index-independent tools (`get_file_skeleton`, `get_function`) parse files directly without requiring an index.

### Tools

| Tool | Description |
|------|-------------|
| `get_file_skeleton` | Returns a structural outline of a file — definition lines only, with visual separators. Useful for understanding file structure without reading the entire file. |
| `get_function` | Extracts a specific function by name, with resolved imports and class context. Reports "no changes" when the function body hasn't changed since last retrieval. |
| `find_symbol_references` | Finds all definitions and references for a symbol name across the project. Returns file paths and line/column ranges. |
| `replace_symbol` | Replaces an entire symbol definition using extended AST ranges (includes preceding comments, docstrings, decorators, and export keywords). Applies multiple replacements atomically. |
| `rename_symbol` | Renames an identifier across all files using line/column positions from the symbol index. Edits are applied atomically per file. |

### Commands

| Command | Description |
|---------|-------------|
| `/reindex-ast` | Force a full re-scan of the project for AST symbol indexing. Use when the index is stale or after bulk file changes. |

### Configuration

AST settings in `~/.stupidex/config.json`:

| Field | Default | Description |
|-------|---------|-------------|
| `ast_max_file_size` | `1048576` | Skip files larger than this (bytes, 1 MB) |

Environment variable override: `STUPIDEX_AST_MAX_FILE_SIZE`.

The AST index is stored in `.stupidex/ast/symbols.db` (excluded from git via `.gitignore`). The `ignored_dirs` config field is shared with RAG — both subsystems skip the same directories.

### Future Languages

The following languages are planned for future releases: Rust, Go, C/C++, C#, Ruby, Java, PHP, Swift, Kotlin.

## MCP (Model Context Protocol)

The project includes a full MCP client for connecting to external tool servers. MCP servers are configured in `~/.stupidex/config.json` and started automatically on app launch.

### Default Servers

**Context7** is included by default — it provides up-to-date, version-specific documentation for any library or framework. Requires `npx` (install [Node.js](https://nodejs.org/) if not available).

**Example** is a minimal reference server for testing and learning. Agents can use `mcp_example_echo` to verify MCP connectivity.

Agents can use Context7 tools (`mcp_context7_resolve-library-id`, `mcp_context7_query-docs`) to fetch fresh docs during code generation and exploration.

### Configuration

MCP servers are configured under `mcp_servers` in `~/.stupidex/config.json`:

```json
{
  "mcp_servers": {
    "context7": {
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp"]
    },
    "filesystem": {
      "command": "mcp-server-filesystem",
      "args": ["/home/user/projects"]
    }
  }
}
```

**stdio servers** use `command` (string) + `args` (list, optional) + `env` (object, optional). **HTTP/SSE servers** use `url`.

Project-level config (`.stupidex.json`) merges with home config — project entries override same-name home entries.

### Agent Access

Agents access MCP tools through `allowed_tools` glob patterns in their `AGENT.md`:

```yaml
allowed_tools:
  - mcp_context7_*    # All Context7 tools
  - mcp_*             # All MCP tools
```

### Available Tools

Each MCP server's tools are registered as `mcp_<server_name>_<tool_name>`. Server names must match `[a-z0-9-]+`.

The `read_mcp_resource` meta-tool lets agents read resources exposed by MCP servers (files, schemas, etc.) by URI.

### Bundled Example Server

A minimal example server is included for development and testing:

```bash
python -m stupidex.mcp.example_server
```

Exposes one tool (`echo`) and one resource (`example://stupidex`).

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
      providers.py              # Provider resolution + model metadata hydration
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
      ast.py                   # AST tools (skeleton, function, references, replace, rename)
      mcp_resource.py          # MCP resource read tool
    mcp/                       # MCP client
      __init__.py              # MCPManager, lifecycle, ContextVar accessor
      schema.py                # MCP tool schema conversion
      example_server.py        # Bundled example MCP server
    rag/                       # RAG pipeline
      chunker.py               # Language-aware file chunking
      embedder.py              # Embedding provider abstraction
      indexer.py               # Project indexing orchestrator
      store.py                 # SQLite + numpy vector store
    ast/                       # AST tools subsystem
      parser.py                # Tree-sitter lazy loader + query cache
      store.py                 # AST symbol index (SQLite + WAL)
      indexer.py               # Walk + parse + symbol extract + hash
      symbols.py               # Symbol dataclass
      queries/
        python.scm             # S-expression query for Python
        javascript.scm         # S-expression query for JavaScript
        typescript.scm         # S-expression query for TypeScript (reused by TSX)
    widgets/
      message_widget.py        # Textual widgets for messages
      sidebar.py               # Right sidebar
```

## Providers

Stupidex supports multiple LLM providers simultaneously. Each provider is an entry under the `providers` key in `~/.stupidex/config.json`, identified by an alias. Model references throughout the config use the `alias/model` format (e.g. `"default/mimo-v2.5"`) so the routing layer knows which provider to use for each call.

### Provider Entry Fields

| Field | Required | Description |
|-------|----------|-------------|
| `base_url` | No | Endpoint URL. Omit for native providers (e.g. `anthropic`) where litellm supplies the URL. |
| `litellm_provider` | No | litellm provider name (e.g. `"openai"`, `"anthropic"`, `"azure"`). Used to route the call and look up model metadata. |
| `api_key` | No | Literal API key. Mutually exclusive with `api_key_env` (if both set, `api_key_env` is dropped). |
| `api_key_env` | No | Name of an env var holding the API key (e.g. `"OPENAI_API_KEY"`). |
| `models` | No | Dict of `{model_id: {override_fields}}`. Declares which models appear in the `/model` picker. Resolution still works for undeclared models. |

If neither `api_key` nor `api_key_env` is set, litellm falls back to its own env detection (e.g. `OPENAI_API_KEY`).

**Per-model metadata overrides** (optional, inside each model entry):

| Field | Type | Description |
|-------|------|-------------|
| `max_input_tokens` | int | Override litellm's registry value for context window display. |
| `max_output_tokens` | int | Override litellm's registry value for max output display. |
| `supports_vision` | bool | Force vision badge on/off in the picker. |
| `mode` | str | Force mode (`"chat"`, `"completion"`, `"embedding"`, etc.). |
| `litellm_provider` | str | Override the provider-level `litellm_provider` for this model only (used for litellm lookups, not displayed). |

Metadata is resolved by field-level merge: your override wins, litellm's registry fills gaps, text-only defaults cover the rest. Unknown models fall back gracefully to `supports_vision=false`, `mode="chat"`.

### Default Config (first run)

A fresh install seeds a single `default` provider so the app works without any config edits:

```json
{
  "providers": {
    "default": {
      "base_url": "https://opencode.ai/zen/go/v1",
      "litellm_provider": "openai",
      "models": {
        "mimo-v2.5": {}
      }
    }
  },
  "default_model": "default/mimo-v2.5",
  "tier_models": {
    "tolo": "default/mimo-v2.5",
    "tainha": "default/mimo-v2.5",
    "papudo": "default/mimo-v2.5",
    "papaca": "default/mimo-v2.5"
  }
}
```

### Examples

**OpenAI with an inline API key:**

```json
{
  "providers": {
    "openai-prod": {
      "litellm_provider": "openai",
      "api_key": "sk-your-key-here",
      "models": {
        "gpt-4o": {},
        "gpt-4o-mini": {}
      }
    }
  },
  "default_model": "openai-prod/gpt-4o"
}
```

**OpenAI with an env-var reference (recommended — no secrets in config files):**

```json
{
  "providers": {
    "openai-prod": {
      "litellm_provider": "openai",
      "api_key_env": "OPENAI_API_KEY",
      "models": {
        "gpt-4o": {},
        "gpt-4o-mini": {}
      }
    }
  }
}
```

```bash
export OPENAI_API_KEY="sk-your-key-here"
stupidex
```

**Local Ollama (no API key, OpenAI-compatible endpoint):**

```json
{
  "providers": {
    "ollama": {
      "base_url": "http://localhost:11434/v1",
      "litellm_provider": "openai",
      "models": {
        "llama3.1:70b": {"max_input_tokens": 131072, "supports_vision": false},
        "qwen2.5-coder:32b": {"max_input_tokens": 32768}
      }
    }
  },
  "default_model": "ollama/llama3.1:70b"
}
```

**Multiple providers (mix of cloud + local):**

```json
{
  "providers": {
    "openai-prod": {
      "litellm_provider": "openai",
      "api_key_env": "OPENAI_API_KEY",
      "models": {
        "gpt-4o": {"supports_vision": true, "max_output_tokens": 16384},
        "gpt-4o-mini": {}
      }
    },
    "ollama": {
      "base_url": "http://localhost:11434/v1",
      "litellm_provider": "openai",
      "models": {
        "llama3.1:70b": {"max_input_tokens": 131072}
      }
    }
  },
  "default_model": "openai-prod/gpt-4o",
  "tier_models": {
    "tolo": "ollama/llama3.1:70b",
    "tainha": "ollama/llama3.1:70b",
    "papudo": "openai-prod/gpt-4o-mini",
    "papaca": "openai-prod/gpt-4o"
  }
}
```

**Project-level override (`.stupidex.json` in your project root):**

Project config deep-merges with home config. Project providers with the same alias override the home entry; new aliases are added. This lets you add a single model to a provider without clobbering the rest:

```json
{
  "providers": {
    "openai-prod": {
      "models": {
        "gpt-4o": {"max_input_tokens": 32768}
      }
    }
  }
}
```

This merges into the home `openai-prod` provider — `gpt-4o` gets the override, `gpt-4o-mini` is preserved.

### Model Picker

Run `/model` (Ctrl+P → `/model`) to see all configured models across all providers. Each entry shows:

- `alias/model_id` — the reference used internally
- `[vision]` badge — if the model supports vision
- `[text]` badge — if the model mode is `chat` or `completion`
- `128k→16k` — token shorthand (input→output) when metadata is available

**Hybrid discovery (R10).** When a provider entry omits the `models` dict (or leaves it empty), the picker falls back to fetching the provider's `GET /models` endpoint. Well-known models still get badges + token shorthand from litellm's registry; unknown ones appear with `[text]` only. Discovery is cached per-session per-alias; network failures yield an empty list (the picker degrades to "no models for this provider" instead of crashing).

Set `STUPIDEX_DISABLE_MODEL_DISCOVERY=1` (or `true` / `yes`) to enforce strict configured-only behavior — useful for offline use or when you want to limit which models the agent can switch to.

### RAG Embeddings

RAG uses the same `alias/model` format via `rag_embedding_model`. The built-in `fastembed` pseudo-provider handles local ONNX embeddings — see the [RAG](#rag-retrieval-augmented-generation) section for details.

### Reserved Aliases

| Alias | Behavior |
|-------|----------|
| `fastembed` | Reserved for the built-in local ONNX embedding pseudo-provider. Cannot be used as a user-defined provider alias. |

Provider aliases must match `[a-z0-9-]+` (no `/`, underscores, or uppercase).

---

## Configuration

**Location:** `~/.stupidex/config.json`

See [Providers](#providers) for the full schema and examples. A minimal config:

```json
{
  "providers": {
    "default": {
      "base_url": "https://opencode.ai/zen/go/v1",
      "litellm_provider": "openai",
      "models": {
        "mimo-v2.5": {}
      }
    }
  },
  "default_model": "default/mimo-v2.5",
  "tier_models": {
    "tolo": "default/mimo-v2.5",
    "tainha": "default/mimo-v2.5",
    "papudo": "default/mimo-v2.5",
    "papaca": "default/mimo-v2.5"
  },
  "rag_embedding_model": "fastembed/BAAI/bge-small-en-v1.5",
  "mcp_servers": {
    "context7": {
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp"]
    }
  }
}
```

Project-level config: `.stupidex.json` (deep-merges with home config — project entries override same-name home entries, new entries are added).

## TODO - In priority order
- Sandboxing for shell command execution, file operations, and project-level config/agent/skill overrides
  - Arbitrary shell command execution with no sandboxing or allowlist (exec.py)
  - Unrestricted file read/write/edit to arbitrary paths including sensitive system files (file_manipulation.py)
  - 24 bare `except Exception` blocks that silently swallow errors across app.py
  - `write` tool creates arbitrary directory trees with `mkdir(parents=True)` (file_manipulation.py)
  - Error messages leak command strings and file paths in tool execution errors (exec.py)
- Concurrency control for file locking
- LSP
- Approval / permission system
- AGENTS.md handling
  - Also /init command for it
- Session saving to disk
- Web fetch tool or MCP
- ask_question tool

## Subagents
- BTW/Side agent (Ask a question without interrupting the main flow)

## Needs improvement
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
