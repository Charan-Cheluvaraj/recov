import json
from pathlib import Path
from typing import Any, Union

def save_json(data: Any, file_path: Union[str, Path], indent: int = 2) -> None:
    """Save dictionary or list data to JSON file."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)

def load_json(file_path: Union[str, Path]) -> Any:
    """Load dictionary or list data from JSON file."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {file_path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
