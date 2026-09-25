import os
import time
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Tuple, List, Dict, Any

from config import settings
from models.pipeline_result import PipelineResult
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
from recovery.text_reconstruction import (
    reconstruct_small_text_cluster,
    reconstruct_large_text_cluster,
    read_fragment_bytes,
)
from intelligence.scoring import score_reconstructed_file
from intelligence.sensitivity import analyze_sensitivity
from intelligence.priority import calculate_priority_score, rank_reconstructed_candidates
from recovery.recoverability import assess_recoverability
from storage.cache import load_pipeline_cache, save_pipeline_cache, invalidate_pipeline_cache
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

def run_stage_6(
    evidence_path: str, status_callback: Optional[callable] = None
) -> Tuple[Evidence, List[Fragment], List[FeatureVector], Dict[str, Any], List[FragmentCluster], List[str], List[ReconstructedFile]]:
    """
    Execute Stage 6: Stages 1-5 + Decomposed Integrity Scoring (Four Signals + Composite).
    
    Takes Stage 5 reconstructed candidate files, evaluates reconstruction confidence,
    completeness, structural validity, and corruption estimate, and calculates the
    composite integrity score for candidate prioritization.
    
    Returns:
        (evidence, fragments, features, relationship_graph, clusters, orphans, reconstructed_files)
    """
    evidence, fragments, features, graph, clusters, orphans, reconstructed_files = run_stage_5(
        evidence_path, status_callback=status_callback
    )

    status = PipelineStatus()
    if status_callback:
        status.update(PipelineStage.FOUR_SIGNAL_SCORING, 0.4, f"Computing decomposed integrity scores for {len(reconstructed_files)} candidates")
        status_callback(status)

    cluster_map = {c.cluster_id: c for c in clusters}
    scored_files: List[ReconstructedFile] = []

    for recon in reconstructed_files:
        cluster = cluster_map.get(recon.cluster_id)
        scored = score_reconstructed_file(recon, cluster=cluster, fragments=fragments)
        scored_files.append(scored)

    if status_callback:
        status.update(
            PipelineStage.FOUR_SIGNAL_SCORING,
            1.0,
            f"Successfully scored {len(scored_files)} candidates with 4-signal decomposed integrity"
        )
        status_callback(status)

    return evidence, fragments, features, graph, clusters, orphans, scored_files

def run_stage_7(
    evidence_path: str, status_callback: Optional[callable] = None
) -> Tuple[Evidence, List[Fragment], List[FeatureVector], Dict[str, Any], List[FragmentCluster], List[str], List[ReconstructedFile]]:
    """
    Execute Stage 7: Stages 1-6 + Real Recoverability Assessment & Disrupted-File Reconstruction.
    
    Takes Stage 6 scored reconstructed candidates, performs factual recoverability
    assessment (exact recovered bytes, missing/unknown bytes, observed candidate span,
    observed recovery ratio, deterministic status, and machine-generated explanation),
    writes real candidate artifacts into recovered/recovered_<candidate_id>.<ext>,
    and computes candidate SHA-256 digests.
    
    Returns:
        (evidence, fragments, features, relationship_graph, clusters, orphans, assessed_files)
    """
    evidence, fragments, features, graph, clusters, orphans, scored_files = run_stage_6(
        evidence_path, status_callback=status_callback
    )

    status = PipelineStatus()
    if status_callback:
        status.update(PipelineStage.RECONSTRUCTION, 0.8, f"Assessing recoverability for {len(scored_files)} candidates")
        status_callback(status)

    assessed_files: List[ReconstructedFile] = []
    for scored in scored_files:
        assessed = assess_recoverability(scored, fragments=fragments)
        assessed_files.append(assessed)

    if status_callback:
        status.update(
            PipelineStage.STRUCTURAL_VALIDATION,
            1.0,
            f"Successfully assessed recoverability for {len(assessed_files)} candidates and generated recovered artifacts"
        )
        status_callback(status)

    return evidence, fragments, features, graph, clusters, orphans, assessed_files

def run_stage_8(
    evidence_path: str, status_callback: Optional[callable] = None
) -> Tuple[Evidence, List[Fragment], List[FeatureVector], Dict[str, Any], List[FragmentCluster], List[str], List[ReconstructedFile]]:
    """
    Execute Stage 8: Stages 1-7 + Sensitivity Classification & Investigative Priority Ranking.
    
    Inspects recovered candidate artifacts for potential sensitive identifiers (Aadhaar, PAN,
    email, phone, cards, credentials, sensitive keywords), calculates transparent investigative
    priority scores combining integrity, recoverability, validity, sensitivity, and size minus
    penalties, and deterministically ranks candidates for investigator triage.
    
    Returns:
        (evidence, fragments, features, relationship_graph, clusters, orphans, ranked_files)
    """
    evidence, fragments, features, graph, clusters, orphans, assessed_files = run_stage_7(
        evidence_path, status_callback=status_callback
    )

    status = PipelineStatus()
    if status_callback:
        status.update(PipelineStage.INTELLIGENCE_TRIAGE, 0.4, f"Classifying sensitivity for {len(assessed_files)} candidates")
        status_callback(status)

    frag_map = {f.id: f for f in fragments}
    classified_files: List[ReconstructedFile] = []

    for cand in assessed_files:
        cand_id = cand.candidate_id or cand.id

        # Read actual candidate content for inspection
        data_to_scan = b""
        if cand.output_path and os.path.exists(cand.output_path):
            try:
                with open(cand.output_path, "rb") as cf:
                    data_to_scan = cf.read()
            except Exception:
                data_to_scan = b""

        # Fallback to assembled fragment bytes if output file not accessible
        if not data_to_scan and cand.fragment_ids:
            chunks = []
            for fid in cand.fragment_ids:
                if fid in frag_map:
                    chunks.append(read_fragment_bytes(frag_map[fid]))
            data_to_scan = b"".join(chunks)

        # Run deterministic sensitivity analysis
        assessment = analyze_sensitivity(data_to_scan, candidate_id=cand_id)

        cand.sensitivity_level = assessment.sensitivity_level.value
        cand.detected_categories = assessment.detected_categories
        cand.sensitivity_matches = [m.model_dump() for m in assessment.matches]
        cand.sensitivity_hits = [m.model_dump() for m in assessment.matches]

        # Calculate investigative priority
        p_score, p_reason = calculate_priority_score(
            composite_integrity=cand.composite_integrity_score,
            observed_recovery_ratio=cand.observed_recovery_ratio,
            structural_validity=cand.structural_validity,
            recovered_bytes=cand.recovered_bytes,
            sensitivity_level=assessment.sensitivity_level,
            category_count=len(assessment.detected_categories),
            ambiguous=cand.ambiguous,
            corruption_estimate=cand.corruption_estimate,
        )

        cand.priority_score = p_score
        cand.priority_reason = p_reason
        classified_files.append(cand)

    # Sort deterministically by priority score descending with documented tie-breakers
    ranked_files = rank_reconstructed_candidates(classified_files)

    if status_callback:
        status.update(
            PipelineStage.INTELLIGENCE_TRIAGE,
            1.0,
            f"Successfully classified sensitivity and ranked {len(ranked_files)} candidates"
        )
        status_callback(status)

    return evidence, fragments, features, graph, clusters, orphans, ranked_files


def generate_factual_pipeline_summary(
    evidence: Evidence,
    fragments: List[Fragment],
    clusters: List[FragmentCluster],
    reconstructed_files: List[ReconstructedFile],
    total_duration: float,
) -> str:
    """Generate a completely factual, deterministic pipeline summary grounded only in actual values."""
    lines = [
        "============================================================",
        "DIGITAL EVIDENCE RECONSTRUCTION & RECOVERY SUMMARY",
        "============================================================",
        f"Completed: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"Total Processing Duration: {total_duration:.2f} seconds",
        f"Evidence Source: {evidence.source_path}",
        f"Evidence Size: {evidence.metadata.get('size_bytes', 0):,} Bytes",
        f"Evidence SHA-256: {evidence.sha256}",
        "------------------------------------------------------------",
        f"Fragments Carved: {len(fragments)}",
        f"Clusters Formed: {len(clusters)}",
        f"Reconstruction Candidates: {len(reconstructed_files)}",
    ]

    struct_valid_count = sum(1 for r in reconstructed_files if (r.structural_validity or 0.0) >= 1.0)
    sensitive_count = sum(1 for r in reconstructed_files if (r.sensitivity_level or "NONE") != "NONE")
    high_priority_count = sum(1 for r in reconstructed_files if (r.priority_score or 0.0) >= 0.70)

    lines.append(f"Structurally Validated Candidates: {struct_valid_count}")
    lines.append(f"Sensitive Candidates Detected: {sensitive_count}")
    lines.append(f"High-Priority Candidates: {high_priority_count}")
    lines.append("------------------------------------------------------------")
    lines.append("CANDIDATE RECOVERY TRIAGE:")

    if not reconstructed_files:
        lines.append("  No reconstruction candidates produced from current evidence.")
    else:
        for idx, r in enumerate(reconstructed_files, start=1):
            cand_id = r.candidate_id or r.id
            ftype = r.file_type.upper()
            status = r.recovery_status or r.status
            rec_b = r.recovered_bytes
            miss_b = r.missing_or_unknown_bytes
            ratio = r.observed_recovery_ratio * 100.0
            sens = r.sensitivity_level or "NONE"
            score = r.priority_score if r.priority_score is not None else 0.0
            lines.append(
                f"  Rank {idx}: [{cand_id}] Type: {ftype} | Status: {status} | "
                f"Recovered: {rec_b:,} B | Missing: {miss_b:,} B | "
                f"Recovery Ratio: {ratio:.1f}% | Sensitivity: {sens} | Priority: {score:.4f}"
            )
            if r.priority_reason:
                lines.append(f"    Reason: {r.priority_reason}")

    lines.append("============================================================")
    return "\n".join(lines)


def run_full_pipeline(
    evidence_path: str,
    status_callback: Optional[callable] = None,
    force_rerun: bool = False,
) -> PipelineResult:
    """
    Authoritative Main Recovery Pipeline Orchestrator.
    
    Executes Stages 1-8 sequentially ONCE per evidence image/version without redundant reprocessing:
    Stage 1: Evidence Ingestion & Magic-Byte Carving
    Stage 2: Entropy Characterization & Typing
    Stage 3: 64D Feature Vector Fingerprinting
    Stage 4: Relationship Mapping & DBSCAN Clustering
    Stage 5: Candidate File Reconstruction & Structural Validation
    Stage 6: Decomposed 4-Signal Integrity Scoring
    Stage 7: Real Recoverability Assessment & Disk Artifact Generation
    Stage 8: Sensitivity Classification & Investigative Priority Ranking
    
    Caches the complete PipelineResult by evidence SHA-256 + pipeline version for instant subsequent retrieval.
    """
    ev_path = Path(evidence_path)
    if not ev_path.is_file():
        raise FileNotFoundError(f"Evidence file not found: {evidence_path}")

    # Fast chunked SHA-256 calculation to check cache
    hasher = hashlib.sha256()
    with open(ev_path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            hasher.update(chunk)
    evidence_sha256 = hasher.hexdigest()

    # Check cache unless force_rerun is requested
    if not force_rerun:
        cached_result = load_pipeline_cache(evidence_sha256, settings.PIPELINE_VERSION)
        if cached_result:
            cached_result.cached = True
            if status_callback:
                status = PipelineStatus()
                status.update(PipelineStage.INTELLIGENCE_TRIAGE, 1.0, f"Loaded cached analysis for {evidence_sha256[:12]}...")
                status_callback(status)
            return cached_result
    else:
        invalidate_pipeline_cache(evidence_sha256, settings.PIPELINE_VERSION)

    stage_durations: Dict[str, float] = {}
    status = PipelineStatus()

    # --- STAGE 1: Evidence Ingestion & Carving ---
    stage_name = "Stage 1: Evidence Ingestion & Carving"
    try:
        t0 = time.perf_counter()
        if status_callback:
            status.update(PipelineStage.EVIDENCE_HASHING, 0.05, f"[1/8] Ingesting and verifying evidence {ev_path.name}")
            status_callback(status)

        evidence = create_evidence_record(evidence_path)

        if status_callback:
            status.update(PipelineStage.FILE_CARVING, 0.12, f"[2/8] Carving magic-byte fragment signatures...")
            status_callback(status)

        fragments = carve_fragments(evidence_path)
        stage_1_duration = time.perf_counter() - t0
        stage_durations["stage_1_duration"] = stage_1_duration
    except Exception as e:
        raise RuntimeError(f"Pipeline failed at {stage_name}: {e}") from e

    # --- STAGE 2: Entropy Characterization ---
    stage_name = "Stage 2: Entropy Characterization"
    try:
        t0 = time.perf_counter()
        if status_callback:
            status.update(PipelineStage.ENTROPY_ANALYSIS, 0.25, f"[3/8] Characterizing entropy for {len(fragments)} fragments")
            status_callback(status)

        characterized_fragments = [characterize_fragment(f) for f in fragments]
        stage_2_duration = time.perf_counter() - t0
        stage_durations["stage_2_duration"] = stage_2_duration
    except Exception as e:
        raise RuntimeError(f"Pipeline failed at {stage_name}: {e}") from e

    # --- STAGE 3: Fragment Fingerprinting ---
    stage_name = "Stage 3: Fragment Fingerprinting"
    try:
        t0 = time.perf_counter()
        if status_callback:
            status.update(PipelineStage.TFIDF_FINGERPRINTING, 0.38, f"[4/8] Generating 64D feature fingerprints for {len(characterized_fragments)} fragments")
            status_callback(status)

        feature_vectors = fit_and_fingerprint(characterized_fragments)
        stage_3_duration = time.perf_counter() - t0
        stage_durations["stage_3_duration"] = stage_3_duration
    except Exception as e:
        raise RuntimeError(f"Pipeline failed at {stage_name}: {e}") from e

    # --- STAGE 4: Relationship Mapping & DBSCAN Clustering ---
    stage_name = "Stage 4: Relationship Mapping & DBSCAN Clustering"
    try:
        t0 = time.perf_counter()
        if status_callback:
            status.update(PipelineStage.RELATIONSHIP_MAPPING, 0.50, f"[5/8] Mapping relationship graph & running DBSCAN clustering")
            status_callback(status)

        graph = build_relationship_graph(characterized_fragments, feature_vectors)
        clusters, orphans = cluster_fragments(feature_vectors, fragments=characterized_fragments)
        stage_4_duration = time.perf_counter() - t0
        stage_durations["stage_4_duration"] = stage_4_duration
    except Exception as e:
        raise RuntimeError(f"Pipeline failed at {stage_name}: {e}") from e

    # --- STAGE 5: Candidate Reconstruction & Validation ---
    stage_name = "Stage 5: Candidate Reconstruction & Validation"
    try:
        t0 = time.perf_counter()
        if status_callback:
            status.update(PipelineStage.RECONSTRUCTION, 0.62, f"[6/8] Reconstructing candidate files from {len(clusters)} clusters")
            status_callback(status)

        frag_map = {f.id: f for f in characterized_fragments}
        reconstructed_files: List[ReconstructedFile] = []
        for cluster in clusters:
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
        stage_5_duration = time.perf_counter() - t0
        stage_durations["stage_5_duration"] = stage_5_duration
    except Exception as e:
        raise RuntimeError(f"Pipeline failed at {stage_name}: {e}") from e

    # --- STAGE 6: Decomposed Integrity Scoring ---
    stage_name = "Stage 6: Decomposed Integrity Scoring"
    try:
        t0 = time.perf_counter()
        if status_callback:
            status.update(PipelineStage.INTEGRITY_SCORING, 0.75, f"[7/8] Evaluating 4 independent integrity signals for {len(reconstructed_files)} candidates")
            status_callback(status)

        cluster_map = {c.cluster_id: c for c in clusters}
        scored_files: List[ReconstructedFile] = []
        for recon in reconstructed_files:
            cl = cluster_map.get(recon.cluster_id)
            scored = score_reconstructed_file(recon, cluster=cl, fragments=characterized_fragments)
            scored_files.append(scored)
        stage_6_duration = time.perf_counter() - t0
        stage_durations["stage_6_duration"] = stage_6_duration
    except Exception as e:
        raise RuntimeError(f"Pipeline failed at {stage_name}: {e}") from e

    # --- STAGE 7: Real Recoverability Assessment ---
    stage_name = "Stage 7: Real Recoverability Assessment"
    try:
        t0 = time.perf_counter()
        if status_callback:
            status.update(PipelineStage.STRUCTURAL_VALIDATION, 0.85, f"[7/8] Assessing recoverability & writing recovered artifacts for {len(scored_files)} candidates")
            status_callback(status)

        assessed_files: List[ReconstructedFile] = []
        recoverability_results: List[Dict[str, Any]] = []
        for scored in scored_files:
            assessed = assess_recoverability(scored, fragments=characterized_fragments)
            assessed_files.append(assessed)
            recoverability_results.append({
                "candidate_id": assessed.candidate_id or assessed.id,
                "recovery_status": assessed.recovery_status,
                "recovered_bytes": assessed.recovered_bytes,
                "missing_or_unknown_bytes": assessed.missing_or_unknown_bytes,
                "observed_candidate_span": assessed.observed_candidate_span,
                "observed_recovery_ratio": assessed.observed_recovery_ratio,
                "output_path": assessed.output_path,
                "output_sha256": assessed.output_sha256,
            })
        stage_7_duration = time.perf_counter() - t0
        stage_durations["stage_7_duration"] = stage_7_duration
    except Exception as e:
        raise RuntimeError(f"Pipeline failed at {stage_name}: {e}") from e

    # --- STAGE 8: Sensitivity Classification & Investigative Priority Ranking ---
    stage_name = "Stage 8: Sensitivity Classification & Investigative Priority Ranking"
    try:
        t0 = time.perf_counter()
        if status_callback:
            status.update(PipelineStage.INTELLIGENCE_TRIAGE, 0.95, f"[8/8] Classifying sensitivity & ranking {len(assessed_files)} candidates")
            status_callback(status)

        classified_files: List[ReconstructedFile] = []
        sensitivity_results: List[Dict[str, Any]] = []
        for cand in assessed_files:
            cand_id = cand.candidate_id or cand.id
            data_to_scan = b""
            if cand.output_path and os.path.exists(cand.output_path):
                try:
                    with open(cand.output_path, "rb") as cf:
                        data_to_scan = cf.read()
                except Exception:
                    data_to_scan = b""

            if not data_to_scan and cand.fragment_ids:
                chunks = []
                for fid in cand.fragment_ids:
                    if fid in frag_map:
                        chunks.append(read_fragment_bytes(frag_map[fid]))
                data_to_scan = b"".join(chunks)

            assessment = analyze_sensitivity(data_to_scan, candidate_id=cand_id)
            cand.sensitivity_level = assessment.sensitivity_level.value
            cand.detected_categories = assessment.detected_categories
            cand.sensitivity_matches = [m.model_dump() for m in assessment.matches]
            cand.sensitivity_hits = [m.model_dump() for m in assessment.matches]

            p_score, p_reason = calculate_priority_score(
                composite_integrity=cand.composite_integrity_score,
                observed_recovery_ratio=cand.observed_recovery_ratio,
                structural_validity=cand.structural_validity,
                recovered_bytes=cand.recovered_bytes,
                sensitivity_level=assessment.sensitivity_level,
                category_count=len(assessment.detected_categories),
                ambiguous=cand.ambiguous,
                corruption_estimate=cand.corruption_estimate,
            )
            cand.priority_score = p_score
            cand.priority_reason = p_reason
            classified_files.append(cand)
            sensitivity_results.append({
                "candidate_id": cand_id,
                "sensitivity_level": cand.sensitivity_level,
                "detected_categories": cand.detected_categories,
                "match_count": assessment.match_count,
                "priority_score": p_score,
                "priority_reason": p_reason,
            })

        ranked_files = rank_reconstructed_candidates(classified_files)
        stage_8_duration = time.perf_counter() - t0
        stage_durations["stage_8_duration"] = stage_8_duration
    except Exception as e:
        raise RuntimeError(f"Pipeline failed at {stage_name}: {e}") from e

    # Total Timing & Summary
    total_duration = sum(stage_durations.values())
    final_summary = generate_factual_pipeline_summary(
        evidence=evidence,
        fragments=characterized_fragments,
        clusters=clusters,
        reconstructed_files=ranked_files,
        total_duration=total_duration,
    )

    # Build authoritative PipelineResult
    orphan_objs = [f for f in characterized_fragments if f.id in orphans]
    ranked_results = RankedResults(
        evidence_image_hash=evidence_sha256,
        files=ranked_files,
        clusters=clusters,
        orphans=orphan_objs,
    )

    result = PipelineResult(
        pipeline_version=settings.PIPELINE_VERSION,
        evidence_path=str(ev_path.resolve()),
        evidence_sha256=evidence_sha256,
        completed_at=datetime.now(timezone.utc).isoformat(),
        total_duration=total_duration,
        stage_durations=stage_durations,
        cached=False,
        evidence=evidence,
        fragments=characterized_fragments,
        characterized_fragments=characterized_fragments,
        feature_vectors=feature_vectors,
        relationship_graph=graph,
        clusters=clusters,
        orphans=orphans,
        reconstructed_files=ranked_files,
        recoverability_results=recoverability_results,
        sensitivity_results=sensitivity_results,
        ranked_results=ranked_results,
        final_summary=final_summary,
    )

    # Save complete result to cache
    save_pipeline_cache(result)

    if status_callback:
        status.update(
            PipelineStage.INTELLIGENCE_TRIAGE,
            1.0,
            f"Recovery analysis complete in {total_duration:.2f}s ({len(ranked_files)} candidates)",
        )
        status_callback(status)

    return result


def run_pipeline(
    evidence_path: str,
    status_callback: Optional[callable] = None,
    force_rerun: bool = False,
) -> PipelineResult:
    """
    Deferred full 14-stage pipeline interface.
    For the authoritative Stage 1-8 full recovery pipeline, use run_full_pipeline(evidence_path).
    """
    raise NotImplementedError(
        "Full 14-stage pipeline is deferred. Use run_full_pipeline(evidence_path) for the complete Stage 1-8 pipeline."
    )

