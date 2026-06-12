from dataclasses import dataclass


@dataclass
class Skill:
    name: str
    description: str
    location: str
    content: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "location": self.location,
        }
