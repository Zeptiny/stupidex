from dataclasses import dataclass

import httpx

from stupidex.config import get_config

_REQUEST_TIMEOUT = 10.0


@dataclass
class Model:
    id: str


async def list_models() -> list[Model]:
    cfg = get_config()
    try:
        async with httpx.AsyncClient(base_url=cfg.base_url, timeout=_REQUEST_TIMEOUT) as client:
            response = await client.get("/models")
            response.raise_for_status()
            data = response.json()
            return [Model(id=model["id"]) for model in data["data"]]
    except (httpx.HTTPError, httpx.TimeoutException):
        return []
