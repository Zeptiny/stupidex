from dataclasses import dataclass
import httpx

@dataclass
class Model:
    id: str
    
def listModels() -> list[Model]:
    with httpx.Client(base_url="https://opencode.ai/zen/go/v1") as client:
        response = client.get("/models")
        response.raise_for_status()
        data = response.json()
        return [Model(id=model["id"]) for model in data["data"]]