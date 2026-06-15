import asyncio
import logging
from pathlib import Path

from stupidex.config import get_config
from stupidex.domain.tool import ExecutorResult, Tool, ToolParameter, ToolParameterProperties
from stupidex.rag.embedder import Embedder, EmbeddingError
from stupidex.rag.indexer import IndexResult, clear_index, get_status, index_project
from stupidex.rag.store import RAGStore

logger = logging.getLogger(__name__)

rag_search_tool = Tool(
    name="rag_search",
    description="Search codebase semantically. Returns code snippets ranked by semantic relevance. Use when grep/glob are insufficient for finding concepts by meaning rather than exact text.",
    parameters=ToolParameter(
        properties={
            "query": ToolParameterProperties(
                type="string",
                description="The semantic search query describing what you're looking for",
            ),
            "top_k": ToolParameterProperties(
                type="integer",
                description="Maximum number of results to return (default: 5)",
            ),
            "file_pattern": ToolParameterProperties(
                type="string",
                description="Glob pattern to filter results (e.g., '*.py', 'src/**/*.ts'). Optional.",
            ),
        },
        required=["query"],
    ),
    action_label="Searching semantically...",
)

rag_index_tool = Tool(
    name="rag_index",
    description="Check RAG index status, trigger re-indexing, or clear the index.",
    parameters=ToolParameter(
        properties={
            "action": ToolParameterProperties(
                type="string",
                description="The action to perform: 'status' to check index state, 'index' to (re)index the project, 'clear' to delete the index.",
            ),
        },
        required=["action"],
    ),
    action_label="Managing RAG index...",
)


async def execute_rag_search(
    query: str,
    top_k: int | None = None,
    file_pattern: str | None = None,
) -> ExecutorResult:
    if not query or not query.strip():
        return ExecutorResult(
            display="Empty query",
            content="Error: 'query' is required and cannot be empty.",
        )

    cfg = get_config()
    project_path = str(Path.cwd())
    store = RAGStore(project_path)

    if top_k is None:
        top_k = cfg.rag_top_k
    if top_k <= 0:
        return ExecutorResult(
            display="Invalid top_k",
            content="Error: top_k must be a positive integer.",
        )

    pre_check = store.status()
    if pre_check.last_indexed is None and pre_check.total_chunks == 0:
        return ExecutorResult(
            display="No RAG index",
            content=(
                "No RAG index found for this project.\n"
                "Use the `rag_index` tool with action='index' to create one, "
                "or run `/index` in the command palette."
            ),
        )

    try:
        embedder = Embedder(
            model=cfg.rag_embedding_model or None,
            provider_api_type=cfg.provider_api_type,
            embedding_provider=cfg.rag_embedding_provider,
        )
        query_embedding = await embedder.embed_single(query)
    except EmbeddingError as e:
        return ExecutorResult(
            display="Embedding failed",
            content=(
                f"Error: Could not generate embedding for query.\n{e}\n\n"
                "Tip: Make sure your LLM provider is configured correctly in config.json."
            ),
        )
    except Exception as e:
        logger.warning("Unexpected embedding error: %s", e)
        return ExecutorResult(
            display="Embedding error",
            content=f"Error generating embedding: {e}",
        )

    loop = asyncio.get_running_loop()
    results = await loop.run_in_executor(
        None, store.search, query_embedding, top_k, file_pattern
    )

    if not results:
        return ExecutorResult(
            display="No results",
            content=f"No results found for query: '{query}'",
        )

    lines = [f"Found {len(results)} result(s) for: '{query}'\n"]
    for i, r in enumerate(results, 1):
        lines.append(
            f"--- Result {i} (score: {r.score:.3f}) ---\n"
            f"File: {r.file_path}:{r.start_line}-{r.end_line}\n"
            f"Language: {r.language}\n"
            f"```\n{r.content}\n```"
        )

    return ExecutorResult(
        display=f"Found {len(results)} semantic matches",
        content="\n".join(lines),
    )


async def execute_rag_index(
    action: str,
) -> ExecutorResult:
    if action not in ("status", "index", "clear"):
        return ExecutorResult(
            display="Invalid action",
            content=(
                f"Error: Unknown action '{action}'. "
                "Must be one of: status, index, clear."
            ),
        )

    project_path = str(Path.cwd())

    if action == "status":
        status = get_status(project_path)
        if status.last_indexed is None and status.total_chunks == 0:
            return ExecutorResult(
                display="No RAG index",
                content="No RAG index exists for this project. Use action='index' to create one.",
            )
        return ExecutorResult(
            display="RAG index status",
            content=(
                f"RAG Index Status:\n"
                f"  Files indexed: {status.total_files}\n"
                f"  Total chunks: {status.total_chunks}\n"
                f"  Embedding model: {status.embedding_model or 'auto-detect'}\n"
                f"  Last indexed: {status.last_indexed or 'never'}"
            ),
        )

    if action == "clear":
        clear_index(project_path)
        return ExecutorResult(
            display="RAG index cleared",
            content="RAG index cleared successfully.",
        )

    # action == "index"
    cfg = get_config()
    embedder = Embedder(
        model=cfg.rag_embedding_model or None,
        provider_api_type=cfg.provider_api_type,
        embedding_provider=cfg.rag_embedding_provider,
    )

    progress_info: list[str] = []

    def _progress(filepath: str, done: int, total: int) -> None:
        if done % 5 == 0 or done == total - 1:
            progress_info.append(f"[{done + 1}/{total}] {filepath}")

    try:
        result: IndexResult = await index_project(
            project_path=project_path,
            force=False,
            embedder=embedder,
            progress_callback=_progress,
        )
    except EmbeddingError as e:
        return ExecutorResult(
            display="Indexing failed",
            content=(
                f"Error: Embedding failed during indexing.\n{e}\n\n"
                "Tip: Make sure your LLM provider is configured correctly in config.json."
            ),
        )
    except Exception as e:
        logger.warning("Indexing failed: %s", e)
        return ExecutorResult(
            display="Indexing failed",
            content=f"Error during indexing: {e}",
        )

    lines = ["RAG Index Complete:\n"]
    lines.append(f"  Files scanned: {result.files_scanned}")
    lines.append(f"  Files indexed: {result.files_indexed}")
    lines.append(f"  Files skipped (unchanged): {result.files_skipped}")
    lines.append(f"  Files deleted: {result.files_deleted}")
    lines.append(f"  Chunks created: {result.chunks_created}")
    lines.append(f"  Duration: {result.duration_seconds:.1f}s")
    if result.errors:
        lines.append(f"\n  Errors ({len(result.errors)}):")
        for err in result.errors[:10]:
            lines.append(f"    - {err}")
    if result.files_indexed == 0 and result.files_skipped == 0 and not result.errors:
        lines.append("\n  No indexable files found in this project.")

    return ExecutorResult(
        display=f"Indexed {result.files_indexed} files ({result.chunks_created} chunks)",
        content="\n".join(lines),
    )
