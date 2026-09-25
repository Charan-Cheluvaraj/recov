from typing import Optional, Tuple, List, Dict, Any
from models.ranked_results import RankedResults
from models.evidence import Evidence
from models.fragment import Fragment
from models.feature_vector import FeatureVector
from models.cluster import FragmentCluster
from models.reconstructed_file import ReconstructedFile
from recovery.evidence_hash import create_evidence_record
from recovery.carving import carve_fragments
from recovery.entropy import characterize_fragment
from recovery.fingerprinting import fit_and_fingerprint
from recovery.relationship_graph import build_relationship_graph
from recovery.clustering import cluster_fragments
from recovery.reconstruction import reconstruct_structured_file
from recovery.text_reconstruction import reconstruct_small_text_cluster, reconstruct_large_text_cluster
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

def run_stage_3(
    evidence_path: str, status_callback: Optional[callable] = None
) -> Tuple[Evidence, List[Fragment], List[FeatureVector]]:
    """
    Execute Stage 3: Stage 1 (carving) + Stage 2 (characterization) + Stage 3 (fingerprinting).
    
    Returns:
        (Evidence record, list of characterized Fragment objects, list of FeatureVector objects)
    """
    evidence, fragments = run_stage_2(evidence_path, status_callback=status_callback)

    status = PipelineStatus()
    if status_callback:
        status.update(PipelineStage.FRAGMENT_ANALYSIS, 0.9, f"Generating feature vectors for {len(fragments)} fragments")
        status_callback(status)

    features = fit_and_fingerprint(fragments)

    if status_callback:
        status.update(PipelineStage.FRAGMENT_ANALYSIS, 1.0, f"Fingerprinted {len(features)} feature vectors")
        status_callback(status)

    return evidence, fragments, features

def run_stage_4(
    evidence_path: str, status_callback: Optional[callable] = None
) -> Tuple[Evidence, List[Fragment], List[FeatureVector], Dict[str, Any], List[FragmentCluster], List[str]]:
    """
    Execute Stage 4: Stage 1 + Stage 2 + Stage 3 + Stage 4 (Relationship Graph & DBSCAN Clustering).
    
    Returns:
        (evidence, fragments, features, relationship_graph, clusters, orphans)
    """
    evidence, fragments, features = run_stage_3(evidence_path, status_callback=status_callback)

    status = PipelineStatus()
    if status_callback:
        status.update(PipelineStage.RELATIONSHIP_MAPPING, 0.5, f"Constructing relationship graph for {len(fragments)} fragments")
        status_callback(status)

    graph = build_relationship_graph(fragments, features)

    if status_callback:
        status.update(PipelineStage.FRAGMENT_CLUSTERING, 0.8, f"Clustering {len(features)} feature vectors with DBSCAN")
        status_callback(status)

    clusters, orphans = cluster_fragments(features, fragments=fragments)

    if status_callback:
        status.update(PipelineStage.FRAGMENT_CLUSTERING, 1.0, f"Generated {len(clusters)} clusters and {len(orphans)} orphans")
        status_callback(status)

    return evidence, fragments, features, graph, clusters, orphans

def run_stage_5(
    evidence_path: str, status_callback: Optional[callable] = None
) -> Tuple[Evidence, List[Fragment], List[FeatureVector], Dict[str, Any], List[FragmentCluster], List[str], List[ReconstructedFile]]:
    """
    Execute Stage 5: Stages 1-4 + Candidate File Reconstruction and Structural Validation.
    
    Takes Stage 4 clusters, attempts deterministic reconstruction of candidate files,
    writes them to recovered/, validates them against real parsers (Pillow, pypdf/PyPDF2,
    python-docx, zipfile, sqlite3), records gap metadata and parser outcome, and returns
    ReconstructedFile objects.
    
    Returns:
        (evidence, fragments, features, relationship_graph, clusters, orphans, reconstructed_files)
    """
    evidence, fragments, features, graph, clusters, orphans = run_stage_4(
        evidence_path, status_callback=status_callback
    )

    status = PipelineStatus()
    if status_callback:
        status.update(PipelineStage.RECONSTRUCTION, 0.2, f"Reconstructing candidate files from {len(clusters)} clusters")
        status_callback(status)

    frag_map = {f.id: f for f in fragments}
    reconstructed_files: List[ReconstructedFile] = []

    for i, cluster in enumerate(clusters):
        member_frags = [frag_map[fid] for fid in cluster.member_fragment_ids if fid in frag_map]
        inferred = (cluster.inferred_type or "").lower()

        if inferred in ("text", "txt"):
            if len(member_frags) <= 6:
                recon = reconstruct_small_text_cluster(cluster, member_frags)
            else:
                recon = reconstruct_large_text_cluster(cluster, member_frags)
        else:
            recon = reconstruct_structured_file(cluster, member_frags)

        reconstructed_files.append(recon)

    if status_callback:
        status.update(
            PipelineStage.STRUCTURAL_VALIDATION,
            1.0,
            f"Reconstructed and structurally validated {len(reconstructed_files)} file candidates"
        )
        status_callback(status)

    return evidence, fragments, features, graph, clusters, orphans, reconstructed_files

def run_pipeline(evidence_path: str, status_callback: Optional[callable] = None) -> RankedResults:
    """
    Main 14-stage Pipeline Orchestrator.
    
    Stages 6-14 are intentionally deferred; use run_stage_1 .. run_stage_5 for completed stages.
    """
    context = PipelineContext(evidence_path=evidence_path)
    status = PipelineStatus()

    if status_callback:
        status.update(PipelineStage.EVIDENCE_HASHING, 0.05, "Calculating evidence SHA-256")
        status_callback(status)

    raise NotImplementedError(
        "Full 14-stage pipeline is deferred in Stage 5. "
        "Use run_stage_5(evidence_path) for Stage 5 candidate file reconstruction and validation."
    )