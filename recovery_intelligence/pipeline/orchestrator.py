from typing import Optional, Tuple, List
from models.ranked_results import RankedResults
from models.evidence import Evidence
from models.fragment import Fragment
from recovery.evidence_hash import create_evidence_record
from recovery.carving import carve_fragments
from .pipeline_context import PipelineContext
from .pipeline_status import PipelineStatus, PipelineStage

def run_stage_1(
    evidence_path: str, status_callback: Optional[callable] = None
) -> Tuple[Evidence, List[Fragment]]:
    """
    Execute Stage 1: Evidence validation, SHA-256 calculation, and magic-byte carving.
    
    Returns:
        (Evidence record, list of candidate Fragment objects)
    """
    status = PipelineStatus()
    if status_callback:
        status.update(PipelineStage.EVIDENCE_HASHING, 0.1, "Validating and calculating SHA-256")
        status_callback(status)

    evidence = create_evidence_record(evidence_path)

    if status_callback:
        status.update(PipelineStage.FILE_CARVING, 0.5, f"Carving fragments from {evidence.metadata.get('file_name', '')}")
        status_callback(status)

    fragments = carve_fragments(evidence_path)

    if status_callback:
        status.update(PipelineStage.FILE_CARVING, 1.0, f"Carved {len(fragments)} candidate fragments")
        status_callback(status)

    return evidence, fragments

def run_pipeline(evidence_path: str, status_callback: Optional[callable] = None) -> RankedResults:
    """
    Main 14-stage Pipeline Orchestrator.
    
    Stages 2-14 are intentionally deferred; use run_stage_1(evidence_path) for Stage 1.
    """
    context = PipelineContext(evidence_path=evidence_path)
    status = PipelineStatus()

    if status_callback:
        status.update(PipelineStage.EVIDENCE_HASHING, 0.05, "Calculating evidence SHA-256")
        status_callback(status)

    raise NotImplementedError(
        "Full 14-stage pipeline is deferred in Stage 1. "
        "Use run_stage_1(evidence_path) for Stage 1 evidence ingestion and carving."
    )
