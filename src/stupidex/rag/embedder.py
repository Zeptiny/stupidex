import asyncio
import logging

logger = logging.getLogger(__name__)

DEFAULT_OPENAI_MODEL = "text-embedding-3-small"
BATCH_SIZE = 100
MAX_RETRIES = 3


class EmbeddingError(Exception):
    pass


class Embedder:
    def __init__(self, model: str | None = None, provider_api_type: str = "openai"):
        self.model = model or ""
        self.provider_api_type = provider_api_type

    def _resolve_model(self) -> str:
        if self.model:
            return self.model
        if self.provider_api_type in ("openai",):
            return DEFAULT_OPENAI_MODEL
        return DEFAULT_OPENAI_MODEL

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        model = self._resolve_model()
        logger.debug("Embedding %d texts with model %s", len(texts), model)
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i : i + BATCH_SIZE]
            batch_embeddings = await self._embed_batch(model, batch)
            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    async def _embed_batch(self, model: str, texts: list[str]) -> list[list[float]]:
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
