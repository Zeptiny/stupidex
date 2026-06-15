---
title: "RAG Pipeline: Ingestão → Embedding → Busca → Resposta"
type: feat
status: active
date: 2026-06-13
---

# RAG Pipeline

## Summary

Implementar um pipeline RAG completo no stupidex: ingestão de código-fonte do repositório do utilizador, geração de embeddings via LLM/provider existente, armazenamento num vector store local minimalista (numpy `.npy` + sqlite3), e exposição de uma tool `rag_search` aos agentes para recuperação semântica.

---

## Problem Frame

Os agentes do stupidex dependem actualmente de `grep`, `glob` e `read` para navegar codebases — ferramentas de busca textual/lexical. Para projectos grandes ou quando o utilizador quer encontrar conceitos sem saber os nomes exactos, falta capacidade de busca semântica. O RAG permite: "encontra o código que trata de autenticação" sem saber que o ficheiro se chama `auth.py`.

---

## Requirements

- R1. Pipeline RAG: ingestão → Embedding → busca → resposta
- R2. Vector store com embeddings reais
- R3. Os agentes existentes devem conseguir usar o RAG sem alterações ao fluxo de trabalho
- R4. A indexação deve ser opt-in (comando do utilizador) e armazenada localmente
- R5. Reutilizar o provider de LLM/Embeddings já configurado no `config.json` (via `litellm`)

---

## Scope Boundaries

- **Não inclui**: re-indexação automática em background, web scraping, ingestion de documentos não-fonte
- **Não inclui**: re-ranking ou reranking model
- **Não inclui**: multimodal (imagens, diagrams)
- **Não inclui**: cache de embeddings entre projectos (cada projecto tem a sua store)

---

## Context & Research

### Arquitectura Actual (Relevante)

- **Tool pattern**: Cada tool é um `Tool` dataclass + async executor → `ExecutorResult`. Registadas em `get_tool_registry()` (`src/stupidex/tools/__init__.py`).
- **Config**: `~/.stupidex/config.json` (home) + `.stupidex.json` (project). Campos novos adicionados ao `Config` dataclass (`src/stupidex/config.py`).
- **Agent tools**: Cada agente lista `available_tools` no frontmatter do AGENT.md. Filtragem em `stream_response()` (`src/stupidex/llm/client.py`).
- **LLM client**: Usa `litellm.acompletion` com `base_url` e `provider_api_type` configuráveis. `litellm` suporta também `litellm.aembedding` — sem dependências novas.
- **Dependências**: `textual`, `litellm`, `httpx`, `aiofiles` (Python ≥3.11).
- **Async**: toda a codebase é async, tools usam `asyncio.get_running_loop().run_in_executor()` para operações blocking.

### Decisão: numpy + sqlite3 (Zero dependências pesadas)

**ChromaDB foi descartado** por adicionar ~150MB de dependências — inaceitável para uma ferramenta CLI leve.

**Solução escolhida: numpy + sqlite3**

| Componente | Onde | O quê |
|------------|------|-------|
| Vectores de embedding | `.stupidex/rag/vectors.npy` | Array numpy N×D, rebuilt em cada indexação |
| Metadados dos chunks | `.stupidex/rag/index.db` | SQLite: chunks, ficheiros, hash MD5, estado |
| Metadata do índice | Tabela `meta` no index.db | embedding_model, last_indexed, total_chunks |

**Porquê numpy (não puro stdlib):**
- Busca semântica implica cosine similarity em matrizes grandes (potencialmente 50K × 1536)
- Pure Python: ~2s por query com 50K chunks. Numpy: ~20ms
- numpy é ~25MB, amplamente pré-instalado, e é dependência natural de ferramentas ML
- Fallback para cosine similarity pura se numpy não disponível (com aviso de performance)

**Porquê sqlite3 (não JSON):**
- Suporta queries incrementais (INSERT/UPDATE/DELETE atómicos)
- Evita corrupção por escrita concorrente
- Query nativa: "dá-me os hashes de todos os ficheiros", "remove chunks de ficheiro X"
- Faz parte do stdlib — zero dependência

**Schema do `index.db`:**

```sql
CREATE TABLE chunks (
    chunk_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path   TEXT NOT NULL,
    start_line  INTEGER NOT NULL,
    end_line    INTEGER NOT NULL,
    content     TEXT NOT NULL,
    language    TEXT NOT NULL
);

CREATE TABLE files (
    file_path   TEXT PRIMARY KEY,
    hash        TEXT NOT NULL,
    chunk_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

Os vectores são gravados como `np.ndarray` num ficheiro `.npy` separado. A ordem dos vectores corresponde ao `chunk_id` na tabela `chunks` (índice 0 = chunk_id 1, etc.).

---

## Key Technical Decisions

1. **Embeddings via `litellm.aembedding`**: Usar o mesmo provider configurado no `config.json`. Auto-detect: OpenAI → `text-embedding-3-small`, Ollama/local → modelo do config.

2. **Armazenamento em `.stupidex/rag/`**: Cada projecto tem a sua store. Consistente com `.stupidex/agents/` e `.stupidex/skills/`.

3. **Ingestão via comando `/index`**: O utilizador invoca `/index` na command palette. Executa no contexto do projecto actual.

4. **Chunking por caracteres**: Sem tiktoken. Chunk_size em caracteres (default 2000 ≈ 500 tokens), overlap (default 200). Chunking respeita limites de funções/classes (separadores por linhas em branco).

5. **Indexação full-rebuild**: Cada `/index` re-embeda todos os ficheiros. Simples, previsível. Incremental (só ficheiros alterados) é optimização futura.

6. **Tool `rag_search`**: Expõe busca semântica como tool. Parâmetros: `query`, `top_k`, `file_pattern`.

7. **Tool `rag_index`**: Permite ao agente verificar/reindexar. Parâmetros: `action` (index|status|clear).

---

## Implementation Units

### U1. Configuração e Dependências

**Goal:** Adicionar numpy como dependência e novos campos de configuração para RAG.

**Requirements:** R2, R5

**Dependencies:** None

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/stupidex/config.py`

**Approach:**
- Adicionar `numpy` ao `pyproject.toml` em `dependencies`. (sqlite3 é stdlib, não precisa de add)
- Adicionar ao `Config` dataclass:
  - `rag_embedding_model: str` — modelo de embedding (default: `""`, auto-detect por provider)
  - `rag_chunk_size: int` — tamanho dos chunks em caracteres (default: 2000)
  - `rag_chunk_overlap: int` — overlap entre chunks em caracteres (default: 200)
  - `rag_top_k: int` — default top-k para busca (default: 5)
  - `rag_max_file_size: int` — tamanho máximo de ficheiro em bytes (default: 512000 = 500KB)
- Adicionar constantes em `config.py`:
  - `PROJECT_RAG_DIR = ".stupidex/rag"`
  - `RAG_VECTORS_FILE = "vectors.npy"`
  - `RAG_INDEX_DB = "index.db"`
- Adicionar campos ao `_ENV_MAP` para os novos campos.

**Patterns to follow:**
- `Config` dataclass em `src/stupidex/config.py` — campos existentes como `grep_max_results`, `read_line_limit`
- Constants: como `PROJECT_CONFIG_NAME`, `PROJECT_AGENTS_DIR`

**Test scenarios:**
- Config defaults são correctos quando não há config.json
- Override via env vars funciona (`STUPIDEX_RAG_CHUNK_SIZE`)

**Verification:**
- `ruff check src/` passa
- `numpy` importa sem erros

---

### U2. Core RAG Module — Chunking, Embedding e Store

**Goal:** Criar o módulo core do RAG: chunking de código, geração de embeddings, e vector store minimalista com numpy + sqlite3.

**Requirements:** R1, R2, R5

**Dependencies:** U1

**Files:**
- Create: `src/stupidex/rag/__init__.py`
- Create: `src/stupidex/rag/chunker.py`
- Create: `src/stupidex/rag/embedder.py`
- Create: `src/stupidex/rag/store.py`

**Approach:**

**`chunker.py`** — Chunking de código-fonte:
- Função `chunk_file(file_path: str, content: str, chunk_size: int, overlap: int) -> list[Chunk]`
- `Chunk` dataclass: `file_path`, `content`, `start_line`, `end_line`, `language` (extensão)
- Chunking inteligente para código: respeitar limites de funções/classes (detectar linhas embranco como separadores)
- Ficheiros binários ignorados (detectados por `\0` no conteúdo)
- Ficheiros > `rag_max_file_size` ignorados com warning
- Chunking por caracteres, sem tiktoken (2000 chars ≈ 500 tokens, suficiente para MVP)

**`embedder.py`** — Geração de embeddings:
- Classe `Embedder`:
  - `__init__(model: str | None)` — modelo de embedding, auto-detect se None
  - `async embed(texts: list[str]) -> list[list[float]]` — batch embedding via `litellm.aembedding`
  - Auto-detect: OpenAI → `text-embedding-3-small`, Ollama/local → usar embedding model do config
  - Batch de 100 texts por request, retry exponencial 3x
- Se `litellm.aembedding` falhar, tentar fallback para `litellm.acompletion` com prompt de embedding
- Se numpy não disponível: warn uma vez e usar cosine similarity pura no store

**`store.py`** — Vector store minimalista (numpy + sqlite3):

```python
@dataclass
class SearchResult:
    file_path: str
    content: str
    start_line: int
    end_line: int
    score: float
    language: str

@dataclass
class StoreStatus:
    total_chunks: int
    total_files: int
    embedding_model: str
    last_indexed: str | None
```

- Classe `RAGStore`:
  - `__init__(project_path: str)` — inicializa paths em `.stupidex/rag/`
  - `init_db()` — cria tables se não existem (sqlite3)
  - `upsert(chunks: list[Chunk], embeddings: list[list[float]])` — reescreve vectors.npy + atualiza index.db
  - `search(query_embedding: list[float], top_k: int, file_pattern: str | None) -> list[SearchResult]` — cosine similarity via numpy
  - `clear()` — apaga vectors.npy e index.db
  - `status() -> StoreStatus` — lê de index.db
  - `delete_by_file(file_path: str)` — remove chunks de um ficheiro do index.db (não re-indexa vectores)
  - `get_file_hashes() -> dict[str, str]` — lê tabela files para comparação de hash
- **Busca semântica (core):**
  ```python
  # Em search():
  vectors = np.load(vectors_file)  # N×D array
  query_vec = np.array(query_embedding)  # D array
  similarities = vectors @ query_vec / (np.linalg.norm(vectors, axis=1) * np.linalg.norm(query_vec))
  top_indices = np.argsort(similarities)[-top_k:][::-1]
  # Lookup metadata de cada chunk_id no sqlite3
  ```
- **Fallback sem numpy:** Se numpy não disponível, carregar vectores como lista de listas e usar `sum(a*b for a,b in zip(v,q))` para cosine similarity. Mais lento mas funcional.

**Patterns to follow:**
- Async wrapping: `loop.run_in_executor()` para operações blocking (padrão em `src/stupidex/tools/search.py`)
- Dataclass pattern: como `Tool`, `ExecutorResult` em `src/stupidex/domain/`
- Error handling: `ExecutorResult` com display/content

**Test scenarios:**
- Chunking de um ficheiro Python respeita limites e produz chunks com metadata correcta
- Ficheiro binário é ignorado
- Store upsert + search retorna resultados correctos (usar vectors fictícios)
- Store status reflecte contagem real de chunks
- Search com file_pattern filtra correctamente
- Store sem vectors.npy existente → search retorna 0 resultados sem crash

**Verification:**
- Testes unitários passam
- `ruff check src/rag/` passa

---

### U3. Pipeline de Indexação

**Goal:** Pipeline orquestrado que descobre ficheiros, faz chunking, gera embeddings e armazena.

**Requirements:** R1, R2, R3

**Dependencies:** U1, U2

**Files:**
- Create: `src/stupidex/rag/indexer.py`

**Approach:**
- Classe `Indexer`:
  - `__init__(project_path: str)` — usa `RAGStore` e `Embedder`
  - `async index(force: bool = False) -> IndexResult` — pipeline completo
  - `status() -> IndexStatus` — estado actual da indexação
  - `clear()` — apagar índice e metadata
- Pipeline `index()`:
  1. Descobrir ficheiros: `os.walk` respeitando `ignored_dirs` do config
  2. Filtrar por extensões suportadas (`.py`, `.js`, `.ts`, `.md`, `.json`, `.yaml`, `.toml`, `.rs`, `.go`, `.java`, `.c`, `.cpp`, `.h`)
  3. Calcular hash MD5 de cada ficheiro
  4. Comparar com `get_file_hashes()` da store — se `force=True`, ignorar comparação
  5. Para ficheiros novos/modificados: chunk → embed → upsert
  6. Para ficheiros eliminados: `delete_by_file`
  7. Actualizar meta na store com novo estado
- `IndexResult` dataclass: `files_processed`, `files_skipped`, `files_deleted`, `chunks_created`, `duration_seconds`
- `IndexStatus` dataclass: `total_files`, `total_chunks`, `last_indexed` (timestamp), `embedding_model`
- Operações I/O (os.walk, hash, file reads) em thread executor; embedding via `litellm.aembedding` (já async)

**Patterns to follow:**
- Hashing de ficheiros para invalidação: padrão similar ao `get_config().ignored_dirs` em `search.py`
- Progress reporting via return values (sem UI coupling)

**Test scenarios:**
- Indexação inicial processa todos os ficheiros
- Segunda indexação ignora ficheiros inalterados
- Ficheiro eliminado é removido do índice
- `force=True` re-indexa tudo
- Ficheiros ignorados (`.git`, `node_modules`) não são indexados

**Verification:**
- Indexação de um projecto dummy produce vectors.npy + index.db com chunks
- Busca semântica retorna resultados relevantes

---

### U4. Tool `rag_search`

**Goal:** Tool para os agentes fazerem busca semântica no índice RAG.

**Requirements:** R1, R3

**Dependencies:** U2

**Files:**
- Create: `src/stupidex/tools/rag.py`
- Modify: `src/stupidex/tools/__init__.py`

**Approach:**
- Definir `rag_search_tool` (Tool dataclass):
  - Parâmetros: `query` (string, required), `top_k` (integer, optional, default 5), `file_pattern` (string, optional)
  - Descrição: "Search codebase semantically. Returns code snippets ranked by semantic relevance."
- Executor `execute_rag_search(query, top_k=5, file_pattern=None) -> ExecutorResult`:
  - Gerar embedding do query via `Embedder`
  - Buscar no `RAGStore`
  - Formatar resultado: `file_path:start_line-end_line` + score + content snippet
  - Se índice não existe: mensagem clara a sugerir `/index`
- Registar no `_TOOL_REGISTRY` em `src/stupidex/tools/__init__.py`

**Patterns to follow:**
- Tool definition: como `grep_tool` em `src/stupidex/tools/search.py`
- Error handling: como `execute_grep_tool` — `except Exception` → `ExecutorResult`

**Test scenarios:**
- Busca por query retorna top_k resultados ordenados por relevância
- `file_pattern` filtra resultados
- Índice vazio retorna mensagem helpful
- Query vazia retorna erro claro

**Verification:**
- Tool aparece no registry
- Agente general consegue chamar `rag_search`

---

### U5. Comando `/index` e `/rag`

**Goal:** Comandos para o utilizador gerir o RAG via command palette.

**Requirements:** R1, R4

**Dependencies:** U3

**Files:**
- Modify: `src/stupidex/commands/session_commands.py`

**Approach:**
- Adicionar comando `/index` ao `SessionCommands.COMMANDS`:
  - Executa `Indexer.index()` no projecto actual
  - Mostra progresso e resultado na conversa (via `Message`)
  - Suporta `/index --force` para re-indexação completa
- Adicionar comando `/rag status`:
  - Mostra estado do índice: total de chunks, último indexado, modelo de embedding
- Adicionar comando `/rag clear`:
  - Limpa o índice inteiro
- Comandos injectam uma mensagem de sistema no contexto, que o agente processa

**Patterns to follow:**
- Command pattern em `src/stupidex/commands/session_commands.py`

**Test scenarios:**
- `/index` indexa o projecto e mostra resultado
- `/index` em projecto vazio indexa 0 ficheiros
- `/rag status` mostra informação correcta
- `/rag clear` limpa o índice

**Verification:**
- Comandos aparecem no command palette
- Execução sem erros

---

### U6. Tool `rag_index` (para agentes)

**Goal:** Permitir ao agente verificar/reindexar o RAG via tool.

**Requirements:** R1, R3, R4

**Dependencies:** U3, U4

**Files:**
- Modify: `src/stupidex/tools/rag.py`
- Modify: `src/stupidex/tools/__init__.py`

**Approach:**
- Definir `rag_index_tool` (Tool dataclass):
  - Parâmetro: `action` (string enum: "status" | "index" | "clear"), required
  - Descrição: "Check RAG index status, trigger re-indexing, or clear the index."
- Executor `execute_rag_index(action) -> ExecutorResult`:
  - `status`: retorna info do `Indexer.status()`
  - `index`: executa `Indexer.index()` e retorna `IndexResult`
  - `clear`: executa `Indexer.clear()` e confirma
- Registar no `_TOOL_REGISTRY`

**Patterns to follow:**
- Tool com ações múltiplas: como `todo` tool (`src/stupidex/tools/todo.py`)

**Test scenarios:**
- `action=status` retorna contagem e último indexado
- `action=index` executa pipeline e retorna estatísticas
- `action=clear` limpa e confirma
- Action inválida retorna erro claro

**Verification:**
- Ambas as tools RAG (`rag_search`, `rag_index`) funcionam pelo agente

---

### U7. Integração com Agentes e System Prompt

**Goal:** Tornar as tools RAG disponíveis aos agentes e actualizar o system prompt.

**Requirements:** R1, R3

**Dependencies:** U4, U6

**Files:**
- Modify: `src/stupidex/agents/defaults/general/AGENT.md`
- Modify: `src/stupidex/agents/defaults/explorer/AGENT.md`
- Modify: `src/stupidex/llm/dynamic_system_prompt.py` (opcional)

**Approach:**
- Adicionar `rag_search` e `rag_index` ao `available_tools` do agente `general`
- Adicionar `rag_search` ao `available_tools` do agente `explorer`
- Opcionalmente, no dynamic system prompt: `<rag_indexed>true/false</rag_indexed>` quando o índice existe
- Actualizar system prompt do `explorer` com instrução: "Use `rag_search` para busca semântica quando grep/glob não são suficientes"

**Patterns to follow:**
- Agent definition: `src/stupidex/agents/defaults/general/AGENT.md`
- Dynamic prompt: `src/stupidex/llm/dynamic_system_prompt.py`

**Test scenarios:**
- Agente general consegue usar rag_search
- Explorer consegue usar rag_search
- System prompt inclui info de RAG quando indexado

**Verification:**
- Tool filtering permite rag_search ao agente correcto
- LLM consegue chamar rag_search

---

### U8. Tratamento de Erros e Edge Cases

**Goal:** Robustez do pipeline: erros de I/O, embedding failures, projectos grandes.

**Requirements:** R1, R2

**Dependencies:** U3, U4

**Files:**
- Modify: `src/stupidex/rag/indexer.py`
- Modify: `src/stupidex/rag/embedder.py`
- Modify: `src/stupidex/rag/store.py`
- Modify: `src/stupidex/tools/rag.py`

**Approach:**
- Embedding failure: retry 3x com backoff, falhar graceful com mensagem ao utilizador
- Ficheiro muito grande (>500KB default): skip com warning no output
- Embedding model não disponível: mensagem clara a pedir configuração
- Projecto sem ficheiros indexáveis: mensagem informativa
- vectors.npy corrompido: auto-rebuild (clear + re-index)
- index.db corrompido: auto-rebuild
- Sem numpy disponível: warn uma vez, usar cosine similarity pura (mais lento mas funcional)
- Adicionar logging em todos os módulos RAG

**Patterns to follow:**
- Error handling: `execute_grep_tool` — `except Exception` → `ExecutorResult`

**Test scenarios:**
- Embedding API falha → mensagem de erro clara, não crash
- Ficheiro binário é ignorado sem erro
- Índice corrompido → rebuild automático
- Timeout no embedding → retry e eventual falha graceful
- vectors.npy ausente → search retorna 0 resultados sem crash

**Verification:**
- Nenhum `bare except` nos módulos RAG
- Erros são logged e comunicados ao utilizador

---

### U9. Testes

**Goal:** Cobertura de testes para todo o pipeline RAG.

**Requirements:** R1, R2, R3

**Dependencies:** U2, U3, U4, U5, U6

**Files:**
- Create: `tests/test_rag_chunker.py`
- Create: `tests/test_rag_store.py`
- Create: `tests/test_rag_indexer.py`
- Create: `tests/test_rag_tools.py`

**Approach:**
- **`test_rag_chunker.py`**: chunking de diferentes linguagens, ficheiros vazios, binários, grandes
- **`test_rag_store.py`**: CRUD no store (usar directorio tmp, apagar vectors.npy + index.db no teardown)
- **`test_rag_indexer.py`**: pipeline completo com projecto dummy, invalidação por hash
- **`test_rag_tools.py`**: executors das tools com mocks do store/embedder

**Patterns to follow:**
- Testes existentes: `tests/test_streaming_messages.py`, `tests/test_theme_startup.py`

**Test scenarios:**
- Chunk splitting correcto
- Store persiste e recupera embeddings
- Indexer ignora ficheiros inalterados
- Tools retornam ExecutorResult válido

**Verification:**
- `pytest tests/` passa

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| numpy adiciona ~25MB | Aceitável; é dependência padrão em ML. Fallback puro Python se indisponível |
| Embedding API pode ser cara para projectos grandes | Chunking eficiente, batch de 100, invalidação por hash (futuro incremental) |
| Embedding model pode não estar disponível | Auto-detect + fallback + mensagem clara de configuração |
| Full-rebuild em cada indexação é lento para projectos enormes | Optimização futura: incremental por hash de chunk |
| vectors.npy e index.db podem ficar inconsistentes | Escrita atómica: escrever vectors.tmp.npy → rename; depois actualizar index.db |
| Ficheiros muito grandes podem causar OOM no embedding | Limite de 500KB por ficheiro, batch size limitado |
| sqlite3 concorrência (dois `/index` simultâneos) | Usar WAL mode + timeout de 5s |

---

## Open Questions

### Resolvidas no Plano
- **Vector store:** numpy + sqlite3 (não ChromaDB) — minimalista, sem dependências pesadas
- **Storage location:** `.stupidex/rag/` — consistente com `.stupidex/agents/` e `.stupidex/skills/`
- **Embeddings:** via `litellm.aembedding` — reutiliza config existente
- **Ingestão:** comando `/index` — opt-in, sem overhead automático

### Deferred to Implementation
- **Incremental embedding por chunk**: Actualmente re-embeda tudo por ficheiro. Deferred — simplificação acceptable para MVP.
- **AST-aware chunking**: Chunking inicial por linhas em branco. Futuro: respeitar AST de Python/JS.
- **Multi-project indexing**: Cada projecto é independente.
- **Mmap vectors.npy**: Para projectos com >100K chunks, usar `np.load(mmap_mode='r')` para evitar OOM.
