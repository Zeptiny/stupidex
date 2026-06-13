from dataclasses import dataclass

import httpx

from stupidex.config import get_config


@dataclass
class Model:
    id: str


async def list_models() -> list[Model]:
    cfg = get_config()
    async with httpx.AsyncClient(base_url=cfg.base_url) as client:
        response = await client.get("/models")
        response.raise_for_status()
        data = response.json()
        return [Model(id=model["id"]) for model in data["data"]]
