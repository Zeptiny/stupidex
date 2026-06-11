from dataclasses import dataclass
import httpx
from stupidex.config import get_config


@dataclass
class Model:
    id: str


def list_models() -> list[Model]:
    cfg = get_config()
    with httpx.Client(base_url=cfg.base_url) as client:
        response = client.get("/models")
        response.raise_for_status()
        data = response.json()
        return [Model(id=model["id"]) for model in data["data"]]
