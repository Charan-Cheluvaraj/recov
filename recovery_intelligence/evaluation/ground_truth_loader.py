from pathlib import Path
from typing import Dict, Any
from storage.json_store import load_json
from config import settings

def load_ground_truth(file_path: Path = None) -> Dict[str, Any]:
    """
    Load ground truth metadata map for benchmark evaluation.
    STRICT ISOLATION: Must NEVER be called by recovery pipeline modules.
    """
    target_path = file_path or (settings.DATASET_DIR / "ground_truth.json")
    if not target_path.exists():
        return {}
    return load_json(target_path)
