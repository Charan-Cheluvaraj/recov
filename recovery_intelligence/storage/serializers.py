from typing import Type, TypeVar, Dict, Any
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

def serialize_model(model: BaseModel) -> Dict[str, Any]:
    """Serialize a Pydantic model instance to a JSON-compatible dictionary."""
    return model.model_dump()

def deserialize_model(model_class: Type[T], data: Dict[str, Any]) -> T:
    """Deserialize a JSON dictionary back into a Pydantic model instance."""
    return model_class.model_validate(data)
