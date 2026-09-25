import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import Counter

from models.cluster import FragmentCluster
from models.fragment import Fragment
from models.reconstructed_file import ReconstructedFile
from config.settings import settings
from .validation import validate_reconstruction
from .text_reconstruction import read_fragment_bytes, compute_gap_information


EXTENSION_MAP = {
    "jpeg": ".jpg",
    "jpg": ".jpg",
    "pdf": ".pdf",
    "docx": ".docx",
    "zip": ".zip",
    "sqlite": ".sqlite",
    "sqlite3": ".sqlite",
    "db": ".sqlite",
    "text": ".txt",
    "txt": ".txt",
}


def infer_cluster_file_type(cluster: FragmentCluster, fragments: List[Fragment]) -> str:
    """Infer candidate file type from cluster inferred_type or fragment type hints."""
    if cluster.inferred_type and cluster.inferred_type.lower() not in ("unknown", "raw"):
        return cluster.inferred_type.lower()
    
    # Check fragment type hints
    hints = [f.type_hint.lower() for f in fragments if f.type_hint and f.type_hint.lower() not in ("unknown", "raw")]
    if hints:
        most_common = Counter(hints).most_common(1)[0][0]
        return most_common
    
    # Check first fragment magic bytes
    if fragments:
        first_frag = min(fragments, key=lambda f: (f.offset, f.id))
        raw_b = read_fragment_bytes(first_frag)
        if raw_b.startswith(b"\xff\xd8"):
            return "jpeg"
        elif raw_b.startswith(b"%PDF-"):
            return "pdf"
        elif raw_b.startswith(b"PK\x03\x04"):
            return "zip"
        elif raw_b.startswith(b"SQLite format 3\x00"):
            return "sqlite"
    
    return "unknown"


def reconstruct_structured_file(
    cluster: FragmentCluster,
    fragments: List[Fragment],
    output_dir: Optional[Path] = None,
) -> ReconstructedFile:
    """
    Reconstruct a candidate structured binary or document file from a fragment cluster.
    
    Orders fragment members deterministically by evidence offset, computes gap metadata,
    assembles candidate bytes, writes the candidate to recovered/, and validates with
    the corresponding real parser.
    """
    candidate_id = f"recon_{cluster.cluster_id}"
    out_dir = output_dir or settings.RECOVERED_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    if not fragments:
        return ReconstructedFile(
            id=candidate_id,
            cluster_id=cluster.cluster_id,
            file_type=cluster.inferred_type or "unknown",
            fragment_ids=[],
            gap_information={"has_gaps": False, "gap_count": 0, "total_gap_bytes": 0, "gaps": []},
            structural_validity=0.0,
            status="cluster_only",
            parser_message="No member fragments available in cluster for reconstruction",
            ambiguous=False,
        )

    # 1. Determine candidate file type
    file_type = infer_cluster_file_type(cluster, fragments)
    ext = EXTENSION_MAP.get(file_type, ".bin")
    candidate_path = out_dir / f"{candidate_id}{ext}"

    # 2. Order fragment members deterministically by evidence offset (tie-break by ID)
    ordered_fragments = sorted(fragments, key=lambda f: (f.offset, f.id))

    # 3. Read bytes in read-only mode & compute gap information
    gap_info = compute_gap_information(ordered_fragments)
    
    byte_chunks = []
    for frag in ordered_fragments:
        chunk = read_fragment_bytes(frag)
        byte_chunks.append(chunk)
    
    # 4. Assemble candidate bytes
    assembled_bytes = b"".join(byte_chunks)

    # 5. Write candidate to recovered/ with deterministic name
    with open(candidate_path, "wb") as f_out:
        f_out.write(assembled_bytes)

    # 6. Open candidate using REAL parser
    valid, parser_msg = validate_reconstruction(file_type, assembled_bytes)

    # 7. Record reconstruction result + reason
    if valid:
        status = "reconstructed"
        structural_validity = 1.0
    else:
        status = "validation_failed"
        structural_validity = 0.0

    return ReconstructedFile(
        id=candidate_id,
        cluster_id=cluster.cluster_id,
        file_type=file_type,
        fragment_ids=[f.id for f in ordered_fragments],
        gap_information=gap_info,
        structural_validity=structural_validity,
        status=status,
        parser_message=parser_msg,
        ambiguous=False,
    )
