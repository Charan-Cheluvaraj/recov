import os
import json
from pathlib import Path
from typing import Optional
from models.ranked_results import RankedResults
from models.pipeline_result import PipelineResult
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

def get_pipeline_cache_path(evidence_sha256: str, pipeline_version: Optional[str] = None) -> Path:
    """Derive deterministic cache path from evidence SHA-256 and pipeline version."""
    ver = pipeline_version or settings.PIPELINE_VERSION
    prefix = evidence_sha256[:16] if len(evidence_sha256) >= 16 else evidence_sha256
    return settings.CACHE_DIR / f"pipeline_{prefix}_{ver}.json"

def save_pipeline_cache(result: PipelineResult) -> Path:
    """
    Persist full PipelineResult to cache directory keyed by evidence SHA-256 and pipeline version.
    Large binary artifacts remain on disk in recovered/; only structured metadata is cached.
    """
    settings.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = get_pipeline_cache_path(result.evidence_sha256, result.pipeline_version)
    
    # Ensure ranked_results sub-model is populated
    result.ensure_ranked_results()

    # Dump Pydantic JSON cleanly
    json_str = result.model_dump_json(indent=2)
    with open(cache_path, "w", encoding="utf-8") as f:
        f.write(json_str)

    # Also maintain legacy run_{key}.json for backwards-compatibility
    if result.ranked_results:
        save_cached_results(result.ranked_results, cache_key=result.evidence_sha256)

    return cache_path

def load_pipeline_cache(evidence_sha256: str, pipeline_version: Optional[str] = None) -> Optional[PipelineResult]:
    """
    Load and validate cached PipelineResult.
    Validates SHA-256 hash match, pipeline version match, and integrity of critical fields.
    Discards and returns None if corrupt, version mismatch, or hash mismatch.
    """
    ver = pipeline_version or settings.PIPELINE_VERSION
    cache_path = get_pipeline_cache_path(evidence_sha256, ver)
    if not cache_path.exists():
        return None

    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            raw_text = f.read()
        
        parsed = PipelineResult.model_validate_json(raw_text)

        # Validation assertions
        if parsed.evidence_sha256 != evidence_sha256:
            return None
        if parsed.pipeline_version != ver:
            return None

        # Verify any written recovered files referenced in the cache still exist on disk
        for rf in parsed.reconstructed_files:
            if rf.output_path and not os.path.exists(rf.output_path):
                # Stale artifact reference -> invalidate cache
                return None

        return parsed
    except Exception:
        # Invalid / corrupt cache -> discard and signal recomputation
        try:
            cache_path.unlink(missing_ok=True)
        except Exception:
            pass
        return None

def invalidate_pipeline_cache(evidence_sha256: str, pipeline_version: Optional[str] = None) -> bool:
    """Invalidate and remove cache for specific evidence SHA-256 and pipeline version."""
    ver = pipeline_version or settings.PIPELINE_VERSION
    cache_path = get_pipeline_cache_path(evidence_sha256, ver)
    removed = False
    if cache_path.exists():
        try:
            cache_path.unlink()
            removed = True
        except Exception:
            pass

    # Also check legacy cache
    legacy_path = settings.CACHE_DIR / f"run_{evidence_sha256}.json"
    if legacy_path.exists():
        try:
            legacy_path.unlink()
            removed = True
        except Exception:
            pass

    return removed
