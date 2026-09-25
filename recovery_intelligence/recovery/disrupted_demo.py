import io
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional
from PIL import Image

from config.settings import settings


def generate_damaged_jpeg_evidence(output_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Generate a deterministic synthetic evidence image containing an intentionally
    disrupted JPEG file with a missing middle section.
    
    Layout:
        0..128: Leading sector noise (128 bytes)
        128..378: Region 1 - JPEG header, markers, tables, SOF0 (250 bytes)
        378..506: Missing unallocated gap filled with null sectors (128 bytes)
        506..751: Region 2 - Surviving scan data tail & EOI footer (245 bytes)
        751..879: Trailing noise (128 bytes)
        
    Note: The middle 150 bytes of scan data were destroyed.
    Intact file metadata is stored in the return dict solely for test assertions;
    the recovery pipeline receives ONLY the raw evidence image.
    """
    # 1. Deterministic small valid JPEG
    img = Image.new("RGB", (32, 32), color=(10, 80, 180))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    intact_jpeg = buf.getvalue()
    intact_len = len(intact_jpeg)

    # 2. Split and remove middle portion
    split_point1 = 250
    removed_bytes_len = 150
    split_point2 = split_point1 + removed_bytes_len

    reg1 = intact_jpeg[:split_point1]
    reg2 = intact_jpeg[split_point2:]
    surviving_bytes_total = len(reg1) + len(reg2)

    # 3. Assemble evidence image with unallocated null gap between surviving regions
    leading_noise = b"\x5a\xa5" * 64  # 128 bytes
    gap_bytes = b"\x00" * 128        # 128 bytes unallocated gap
    trailing_noise = b"\x3c\xc3" * 64 # 128 bytes

    evidence_bytes = leading_noise + reg1 + gap_bytes + reg2 + trailing_noise

    # 4. Save to destination
    out_file = output_path or (settings.DATASET_DIR / "disrupted_jpeg_evidence.raw")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "wb") as f:
        f.write(evidence_bytes)

    evidence_sha256 = hashlib.sha256(evidence_bytes).hexdigest()

    return {
        "evidence_path": str(out_file.resolve()),
        "evidence_size": len(evidence_bytes),
        "evidence_sha256": evidence_sha256,
        "ground_truth_intact_size": intact_len,
        "region1_offset": len(leading_noise),
        "region1_len": len(reg1),
        "gap_offset": len(leading_noise) + len(reg1),
        "gap_len": len(gap_bytes),
        "region2_offset": len(leading_noise) + len(reg1) + len(gap_bytes),
        "region2_len": len(reg2),
        "surviving_bytes_total": surviving_bytes_total,
        "removed_from_original": removed_bytes_len,
    }


def generate_disrupted_text_evidence(output_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Generate an evidence image containing a valid text document split across two
    surviving regions with a missing gap. Demonstrates STRUCTURALLY_VALID_PARTIAL recovery.
    """
    p1 = b"INVESTIGATION INCIDENT REPORT\nCASE ID: 2026-CS-0925\nEVIDENCE STATUS: DISRUPTED\n"
    p2 = b"SUMMARY: Secondary fragment survived with full UTF-8 encoding integrity intact.\n"
    
    leading = b"\x00" * 64
    gap = b"\x00" * 96
    trailing = b"\x00" * 64

    evidence_bytes = leading + p1 + gap + p2 + trailing

    out_file = output_path or (settings.DATASET_DIR / "disrupted_text_evidence.raw")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "wb") as f:
        f.write(evidence_bytes)

    return {
        "evidence_path": str(out_file.resolve()),
        "evidence_size": len(evidence_bytes),
        "evidence_sha256": hashlib.sha256(evidence_bytes).hexdigest(),
        "p1_len": len(p1),
        "gap_len": len(gap),
        "p2_len": len(p2),
        "surviving_total": len(p1) + len(p2),
    }
