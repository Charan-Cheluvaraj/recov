import mmap
from pathlib import Path
from typing import List, Union, Optional, Dict, Any, Tuple
from dataclasses import dataclass

from models.fragment import Fragment
from .evidence_hash import validate_evidence_file

@dataclass(frozen=True)
class SignatureDefinition:
    """Definition of a supported magic-byte file signature."""
    type_hint: str
    header: bytes
    footer: Optional[bytes] = None
    default_length: int = 4096
    max_scan_size: int = 15 * 1024 * 1024  # 15 MB sensible max candidate window

# Centralized file signature registry for Stage 1
SIGNATURE_REGISTRY: tuple[SignatureDefinition, ...] = (
    SignatureDefinition(
        type_hint="jpeg",
        header=b"\xff\xd8\xff",
        footer=b"\xff\xd9",
        default_length=4096,
        max_scan_size=15 * 1024 * 1024,
    ),
    SignatureDefinition(
        type_hint="png",
        header=b"\x89PNG\r\n\x1a\n",
        footer=b"IEND",
        default_length=4096,
        max_scan_size=15 * 1024 * 1024,
    ),
    SignatureDefinition(
        type_hint="gif",
        header=b"GIF89a",
        footer=b"\x3b",
        default_length=4096,
        max_scan_size=10 * 1024 * 1024,
    ),
    SignatureDefinition(
        type_hint="gif",
        header=b"GIF87a",
        footer=b"\x3b",
        default_length=4096,
        max_scan_size=10 * 1024 * 1024,
    ),
    SignatureDefinition(
        type_hint="bmp",
        header=b"BM",
        footer=None,
        default_length=4096,
        max_scan_size=20 * 1024 * 1024,
    ),
    SignatureDefinition(
        type_hint="pdf",
        header=b"%PDF-",
        footer=b"%%EOF",
        default_length=4096,
        max_scan_size=25 * 1024 * 1024,
    ),
    SignatureDefinition(
        type_hint="zip",
        header=b"PK\x03\x04",
        footer=b"PK\x05\x06",
        default_length=4096,
        max_scan_size=30 * 1024 * 1024,
    ),
    SignatureDefinition(
        type_hint="sqlite",
        header=b"SQLite format 3\x00",
        footer=None,
        default_length=4096,
        max_scan_size=50 * 1024 * 1024,
    ),
)


def _calculate_sqlite_candidate_length(data: Union[bytes, mmap.mmap], h_pos: int, total_size: int) -> int:
    """Calculate expected SQLite database size from header page size and page count."""
    try:
        # Page size is at byte offset 16-17 (big-endian 16-bit integer)
        if h_pos + 32 <= total_size:
            raw_page_size = int.from_bytes(data[h_pos + 16:h_pos + 18], "big")
            page_size = 65536 if raw_page_size == 1 else raw_page_size
            
            # Page count is at byte offset 28-31 (big-endian 32-bit integer)
            page_count = int.from_bytes(data[h_pos + 28:h_pos + 32], "big")
            
            # Verify power of two between 512 and 65536
            if 512 <= page_size <= 65536 and (page_size & (page_size - 1)) == 0 and page_count > 0:
                expected_size = page_size * page_count
                return min(expected_size, total_size - h_pos)
    except Exception:
        pass
    return min(4096, total_size - h_pos)


def _find_jpeg_candidate_boundary(
    data: Union[bytes, mmap.mmap], h_pos: int, total_size: int, max_scan_size: int
) -> Tuple[int, bool]:
    """
    Format-aware JPEG boundary detection.
    
    1. Scans for EOI (0xFFD9) without crossing a competing JPEG header (0xFFD8FF).
    2. Does not swallow multiple adjacent JPEGs into one oversized candidate.
    3. Stops at the first valid, plausible EOI for this specific image stream.
    """
    max_scan = min(total_size, h_pos + max_scan_size)
    next_soi = data.find(b"\xff\xd8\xff", h_pos + 3, max_scan)
    search_limit = next_soi if next_soi != -1 else max_scan

    # Search for EOI marker within the constrained candidate range
    eoi_pos = data.find(b"\xff\xd9", h_pos + 3, search_limit)
    if eoi_pos != -1:
        cand_len = (eoi_pos + 2) - h_pos
        return cand_len, True

    # No EOI before next header: truncate at next SOI boundary if present
    if next_soi != -1:
        return next_soi - h_pos, False

    return min(4096, total_size - h_pos), False


def _find_pdf_candidate_boundary(
    data: Union[bytes, mmap.mmap], h_pos: int, total_size: int, max_scan_size: int
) -> Tuple[int, bool]:
    """
    Format-aware PDF boundary detection.
    
    Locates the matching %%EOF trailer before any competing %PDF- header.
    """
    max_scan = min(total_size, h_pos + max_scan_size)
    next_pdf = data.find(b"%PDF-", h_pos + 5, max_scan)
    search_limit = next_pdf if next_pdf != -1 else max_scan

    eof_pos = -1
    curr = h_pos + 5
    while curr < search_limit:
        pos = data.find(b"%%EOF", curr, search_limit)
        if pos == -1:
            break
        eof_pos = pos
        curr = pos + 5

    if eof_pos != -1:
        end_pos = eof_pos + 5
        while end_pos < total_size and data[end_pos:end_pos + 1] in (b"\r", b"\n", b" ", b"\x00"):
            end_pos += 1
        return end_pos - h_pos, True

    if next_pdf != -1:
        return next_pdf - h_pos, False

    return min(4096, total_size - h_pos), False


def _find_zip_candidate_boundary(
    data: Union[bytes, mmap.mmap], h_pos: int, total_size: int, max_scan_size: int
) -> Tuple[int, bool, str]:
    """
    Format-aware ZIP/DOCX/XLSX boundary detection via End of Central Directory (PK\x05\x06).
    """
    max_scan = min(total_size, h_pos + max_scan_size)
    eocd_pos = data.find(b"PK\x05\x06", h_pos + 4, max_scan)
    if eocd_pos != -1:
        comment_len = 0
        if eocd_pos + 22 <= total_size:
            comment_len = int.from_bytes(data[eocd_pos + 20:eocd_pos + 22], "little")
        end_pos = min(total_size, eocd_pos + 22 + comment_len)

        # Inspect internal directory clues for DOCX/XLSX/PPTX
        sample = data[h_pos:end_pos]
        type_hint = "zip"
        if b"word/" in sample or b"[Content_Types].xml" in sample:
            type_hint = "docx"
        elif b"xl/" in sample:
            type_hint = "xlsx"
        elif b"ppt/" in sample:
            type_hint = "pptx"

        return end_pos - h_pos, True, type_hint

    return min(4096, total_size - h_pos), False, "zip"


def _carve_candidates_for_header(
    data: Union[bytes, mmap.mmap],
    sig: SignatureDefinition,
    h_pos: int,
    total_size: int,
) -> List[Dict[str, Any]]:
    """
    Determine format-aware fragment boundaries for a candidate signature match.
    Prevents cross-file swallowing and establishes honest candidate boundaries.
    """
    meta: Dict[str, Any] = {
        "signature": sig.header.hex(),
        "detection_method": "format_aware_carving",
    }
    type_hint = sig.type_hint
    has_footer = False
    length = sig.default_length

    if sig.type_hint == "sqlite":
        length = _calculate_sqlite_candidate_length(data, h_pos, total_size)
        has_footer = False
    elif sig.type_hint == "jpeg":
        length, has_footer = _find_jpeg_candidate_boundary(data, h_pos, total_size, sig.max_scan_size)
    elif sig.type_hint == "pdf":
        length, has_footer = _find_pdf_candidate_boundary(data, h_pos, total_size, sig.max_scan_size)
    elif sig.type_hint == "zip":
        length, has_footer, type_hint = _find_zip_candidate_boundary(data, h_pos, total_size, sig.max_scan_size)
    elif sig.type_hint == "png":
        max_scan = min(total_size, h_pos + sig.max_scan_size)
        iend = data.find(b"IEND", h_pos + 8, max_scan)
        if iend != -1:
            length = min(total_size, iend + 8) - h_pos
            has_footer = True
        else:
            length = min(sig.default_length, total_size - h_pos)
    elif sig.type_hint == "bmp":
        if h_pos + 6 <= total_size:
            b_size = int.from_bytes(data[h_pos + 2:h_pos + 6], "little")
            if 54 <= b_size <= sig.max_scan_size:
                length = min(b_size, total_size - h_pos)
                has_footer = True
            else:
                length = min(sig.default_length, total_size - h_pos)
        else:
            length = min(sig.default_length, total_size - h_pos)
    elif sig.type_hint == "gif":
        max_scan = min(total_size, h_pos + sig.max_scan_size)
        tr = data.find(b"\x3b", h_pos + 6, max_scan)
        if tr != -1:
            length = (tr + 1) - h_pos
            has_footer = True
        else:
            length = min(sig.default_length, total_size - h_pos)
    else:
        length = min(sig.default_length, total_size - h_pos)

    end_pos = h_pos + length
    meta["has_footer"] = has_footer
    if has_footer and sig.footer:
        meta["footer_signature"] = sig.footer.hex()

    # Check for unallocated zero gaps (>= 64 contiguous null bytes) inside candidate range (except SQLite)
    null_marker = b"\x00" * 64
    if sig.type_hint != "sqlite" and (h_pos + 64) < end_pos:
        first_gap = data.find(null_marker, h_pos + 32, end_pos - 8)
        if first_gap != -1 and first_gap > h_pos:
            spans = []
            curr = h_pos
            while curr < end_pos:
                gap_idx = data.find(null_marker, curr, end_pos)
                if gap_idx == -1:
                    if end_pos > curr:
                        spans.append((curr, end_pos))
                    break
                if gap_idx > curr:
                    spans.append((curr, gap_idx))
                skip = gap_idx
                while skip < end_pos and data[skip:skip + 1] == b"\x00":
                    skip += 1
                curr = skip

            if len(spans) > 1:
                candidates = []
                group_id = f"disrupted_{type_hint}_{h_pos}"
                for i, (st, en) in enumerate(spans):
                    is_first = (i == 0)
                    is_last = (i == len(spans) - 1)
                    m = {
                        "signature": sig.header.hex() if is_first else "",
                        "footer_signature": (sig.footer.hex() if (has_footer and sig.footer) else "") if is_last else "",
                        "detection_method": "format_aware_disrupted",
                        "has_footer": has_footer if is_last else False,
                        "disrupted_extent_index": i,
                        "disrupted_extent_total": len(spans),
                        "group_id": group_id,
                    }
                    candidates.append({
                        "offset": st,
                        "length": en - st,
                        "type_hint": type_hint,
                        "header_flag": is_first,
                        "footer_flag": is_last and has_footer,
                        "metadata": m,
                    })
                return candidates

    # Return format-aware candidate fragment
    return [{
        "offset": h_pos,
        "length": length,
        "type_hint": type_hint,
        "header_flag": True,
        "footer_flag": has_footer,
        "metadata": meta,
    }]


def carve_fragments(evidence_path: Union[str, Path]) -> List[Fragment]:
    """
    Perform format-aware byte-level carving on an evidence disk/memory image.
    
    Scans the evidence file for supported magic bytes (JPEG, PNG, GIF, BMP, PDF, ZIP/DOCX, SQLite),
    determines conservative candidate boundaries, and generates deterministic Fragment objects.
    
    Args:
        evidence_path: Path to raw evidence image (.dd, .raw, .img, .bin).
        
    Returns:
        List of candidate Fragment objects sorted by start offset.
    """
    path = validate_evidence_file(evidence_path)
    file_size = path.stat().st_size
    candidates: List[dict] = []

    # Read-only memory mapped scanning for safe, low-memory execution
    with open(path, "rb") as f:
        try:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                for sig in SIGNATURE_REGISTRY:
                    search_pos = 0
                    while search_pos < file_size:
                        h_pos = mm.find(sig.header, search_pos)
                        if h_pos == -1:
                            break

                        header_cands = _carve_candidates_for_header(
                            mm, sig, h_pos, file_size
                        )
                        candidates.extend(header_cands)

                        # Advance search position past header
                        search_pos = h_pos + len(sig.header)

        except (OSError, ValueError):
            # Fallback to chunked scanning if mmap is unavailable
            f.seek(0)
            data = f.read()
            for sig in SIGNATURE_REGISTRY:
                search_pos = 0
                while search_pos < file_size:
                    h_pos = data.find(sig.header, search_pos)
                    if h_pos == -1:
                        break

                    header_cands = _carve_candidates_for_header(
                        data, sig, h_pos, file_size
                    )
                    candidates.extend(header_cands)
                    search_pos = h_pos + len(sig.header)

    # Sort candidates deterministically by offset, then by length
    candidates.sort(key=lambda c: (c["offset"], c["length"], c["type_hint"]))

    # Deduplicate exact overlapping signature matches
    unique_candidates: List[dict] = []
    seen: set[tuple[int, int, str]] = set()

    for cand in candidates:
        key = (cand["offset"], cand["length"], cand["type_hint"])
        if key not in seen:
            seen.add(key)
            unique_candidates.append(cand)

    # Construct deterministic Pydantic Fragment models
    fragments: List[Fragment] = []
    source_str = str(path)

    for idx, cand in enumerate(unique_candidates):
        frag_id = f"F{idx + 1:04d}"
        frag_meta = dict(cand["metadata"])
        frag_meta["end_offset"] = cand["offset"] + cand["length"]
        frag_meta["evidence_offset"] = cand["offset"]

        fragment = Fragment(
            id=frag_id,
            offset=cand["offset"],
            length=cand["length"],
            type_hint=cand["type_hint"],
            entropy=0.0,
            source=source_str,
            pipeline_tag="carved",
            header_flag=cand["header_flag"],
            footer_flag=cand["footer_flag"],
            metadata=frag_meta,
        )
        fragments.append(fragment)

    return fragments
