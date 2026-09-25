from typing import Optional, Tuple, List
from models.ranked_results import RankedResults
from models.evidence import Evidence
from models.fragment import Fragment
from recovery.evidence_hash import create_evidence_record
from recovery.carving import carve_fragments
from recovery.entropy import characterize_fragment
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

def run_stage_2(
    evidence_path: str, status_callback: Optional[callable] = None
) -> Tuple[Evidence, List[Fragment]]:
    """
    Execute Stage 2: Stage 1 (ingestion + carving) followed by fragment characterization
    (Shannon entropy, sliding-window analysis, text/binary/mixed characterization).
    
    Returns:
        (Evidence record, list of characterized Fragment objects)
    """
    evidence, fragments = run_stage_1(evidence_path, status_callback=status_callback)

    status = PipelineStatus()
    if status_callback:
        status.update(PipelineStage.FRAGMENT_ANALYSIS, 0.7, f"Analyzing entropy for {len(fragments)} fragments")
        status_callback(status)

    characterized_fragments = [characterize_fragment(f) for f in fragments]

    if status_callback:
        status.update(PipelineStage.FRAGMENT_ANALYSIS, 1.0, f"Characterized {len(characterized_fragments)} fragments")
        status_callback(status)

    return evidence, characterized_fragments

def run_pipeline(evidence_path: str, status_callback: Optional[callable] = None) -> RankedResults:
    """
    Main 14-stage Pipeline Orchestrator.
    
    Stages 3-14 are intentionally deferred; use run_stage_1 / run_stage_2 for completed stages.
    """
    context = PipelineContext(evidence_path=evidence_path)
    status = PipelineStatus()

    if status_callback:
        status.update(PipelineStage.EVIDENCE_HASHING, 0.05, "Calculating evidence SHA-256")
        status_callback(status)

    raise NotImplementedError(
        "Full 14-stage pipeline is deferred in Stage 2. "
        "Use run_stage_2(evidence_path) for Stage 2 evidence ingestion, carving, and characterization."
    )