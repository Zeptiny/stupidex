import asyncio
import logging

logger = logging.getLogger(__name__)

DEFAULT_OPENAI_MODEL = "text-embedding-3-small"
DEFAULT_FASTEMBED_MODEL = "BAAI/bge-small-en-v1.5"
BATCH_SIZE = 100
MAX_RETRIES = 3


class EmbeddingError(Exception):
    pass


class Embedder:
    _fastembed_cache: dict[str, object] = {}

    def __init__(
        self,
        model: str | None = None,
        provider_api_type: str = "openai",
        embedding_provider: str = "",
    ):
        self.model = model or ""
        self.provider_api_type = provider_api_type
        self.embedding_provider = embedding_provider

    def _resolve_provider(self) -> str:
        if self.embedding_provider:
            return self.embedding_provider
        return self.provider_api_type

    def _resolve_model(self) -> str:
        if self.model:
            return self.model
        provider = self._resolve_provider()
        if provider == "openai":
            return DEFAULT_OPENAI_MODEL
        if provider == "fastembed":
            return DEFAULT_FASTEMBED_MODEL
        raise EmbeddingError(
            f"No embedding model configured for provider '{provider}'. "
            "Set 'rag_embedding_model' in config.json or STUPIDEX_RAG_EMBEDDING_MODEL env var."
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        model = self._resolve_model()
        provider = self._resolve_provider()
        logger.debug("Embedding %d texts with %s/%s", len(texts), provider, model)
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i : i + BATCH_SIZE]
            if provider == "fastembed":
                batch_embeddings = await self._embed_fastembed(model, batch)
            else:
                batch_embeddings = await self._embed_litellm(model, batch)
            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    async def _embed_fastembed(self, model: str, texts: list[str]) -> list[list[float]]:
        try:
            from fastembed import TextEmbedding
        except ImportError as err:
            raise EmbeddingError(
                "fastembed is required for local embeddings. "
                "Install it with: pip install fastembed"
            ) from err

        if model not in self._fastembed_cache:
            self._fastembed_cache[model] = await asyncio.to_thread(
                TextEmbedding, model_name=model
            )
        embedder = self._fastembed_cache[model]

        def _run() -> list[list[float]]:
            return [v.tolist() for v in embedder.embed(texts)]

        return await asyncio.to_thread(_run)

    async def _embed_litellm(self, model: str, texts: list[str]) -> list[list[float]]:
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                from litellm import aembedding

                response = await aembedding(model=model, input=texts)
                return [item["embedding"] for item in response.data]
            except ImportError as err:
                raise EmbeddingError(
                    "litellm is required for embeddings. "
                    "Install it with: pip install litellm"
                ) from err
            except Exception as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    wait = 2**attempt
                    logger.warning(
                        "Embedding attempt %d failed (%s), retrying in %ds...",
                        attempt + 1,
                        e,
                        wait,
                    )
                    await asyncio.sleep(wait)

        raise EmbeddingError(
            f"Embedding failed after {MAX_RETRIES} attempts: {last_error}\n"
            "Check your embedding model configuration in config.json or set "
            "STUPIDEX_RAG_EMBEDDING_MODEL env var."
        )

    async def embed_single(self, text: str) -> list[float]:
        results = await self.embed([text])
        return results[0]
