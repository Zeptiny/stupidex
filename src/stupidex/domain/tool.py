from dataclasses import dataclass


@dataclass
class ExecutorResult:
    display: str
    content: str


@dataclass
class ToolParameterProperties:
    type: str
    description: str


@dataclass
class ToolParameter:
    properties: dict[str, ToolParameterProperties]  # name -> schema
    required: list[str]
    type: str = "object"
    additional_properties: bool = False


@dataclass
class Tool:
    name: str
    description: str
    parameters: ToolParameter
    type: str = "function"
    strict: bool = True

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": self.parameters.type,
                    "properties": {
                        k: {"type": v.type, "description": v.description}
                        for k, v in self.parameters.properties.items()
                    },
                    "required": self.parameters.required,
                    "additionalProperties": self.parameters.additional_properties,
                },
                "strict": self.strict,
            },
        }
