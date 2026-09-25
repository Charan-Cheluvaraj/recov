from pathlib import Path
from typing import Optional
from models.ranked_results import RankedResults
from config import settings
from .json_store import save_json, load_json
from .serializers import serialize_model, deserialize_model

def save_cached_results(results: RankedResults, cache_key: Optional[str] = None) -> Path:
    """Save pipeline RankedResults into cache directory for instant demo loading."""
    key = cache_key or results.evidence_image_hash or "default_run"
    cache_path = settings.CACHE_DIR / f"run_{key}.json"
    data = serialize_model(results)
    save_json(data, cache_path)
    return cache_path

def load_cached_results(cache_key: str) -> Optional[RankedResults]:
    """Load cached RankedResults by key/hash if available."""
    cache_path = settings.CACHE_DIR / f"run_{cache_key}.json"
    if not cache_path.exists():
        return None
    data = load_json(cache_path)
    return deserialize_model(RankedResults, data)
