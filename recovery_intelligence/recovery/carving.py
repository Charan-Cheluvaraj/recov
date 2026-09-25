import mmap
from pathlib import Path
from typing import List, Union, Optional, Dict, Any
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
    max_scan_size: int = 50 * 1024 * 1024  # 50 MB max candidate window

# Centralized file signature registry for Stage 1
SIGNATURE_REGISTRY: tuple[SignatureDefinition, ...] = (
    SignatureDefinition(
        type_hint="jpeg",
        header=b"\xff\xd8\xff",
        footer=b"\xff\xd9",
        default_length=4096,
    ),
    SignatureDefinition(
        type_hint="pdf",
        header=b"%PDF-",
        footer=b"%%EOF",
        default_length=4096,
    ),
    SignatureDefinition(
        type_hint="zip",
        header=b"PK\x03\x04",
        footer=b"PK\x05\x06",
        default_length=4096,
    ),
    SignatureDefinition(
        type_hint="sqlite",
        header=b"SQLite format 3\x00",
        footer=None,
        default_length=4096,
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

def _carve_candidates_for_header(
    data: Union[bytes, mmap.mmap],
    sig: SignatureDefinition,
    h_pos: int,
    total_size: int,
) -> List[Dict[str, Any]]:
    """
    Determine fragment boundaries for a candidate signature match.
    
    If the file is disrupted across an unallocated gap (>=64 null bytes) before its footer,
    carves the surviving header fragment and continuation fragment(s) as distinct fragments
    sharing a candidate group ID.
    """
    meta: Dict[str, Any] = {
        "signature": sig.header.hex(),
        "detection_method": "magic_bytes",
    }

    if sig.type_hint == "sqlite":
        length = _calculate_sqlite_candidate_length(data, h_pos, total_size)
        meta["has_footer"] = False
        return [{
            "offset": h_pos,
            "length": length,
            "type_hint": sig.type_hint,
            "header_flag": True,
            "footer_flag": False,
            "metadata": meta,
        }]

    # For formats with footers (JPEG, PDF, ZIP)
    if sig.footer is not None:
        search_limit = min(total_size, h_pos + sig.max_scan_size)
        f_pos = data.find(sig.footer, h_pos + len(sig.header), search_limit)
        
        if f_pos != -1:
            end_pos = f_pos + len(sig.footer)
            
            # Format-specific footer adjustments
            if sig.type_hint == "pdf":
                while end_pos < total_size and data[end_pos:end_pos + 1] in (b"\r", b"\n"):
                    end_pos += 1
            elif sig.type_hint == "zip":
                if f_pos + 22 <= total_size:
                    comment_len = int.from_bytes(data[f_pos + 20:f_pos + 22], "little")
                    end_pos = min(total_size, f_pos + 22 + comment_len)
            
            # Check for unallocated / zero gaps between surviving regions
            null_marker = b"\x00" * 64
            first_gap = data.find(null_marker, h_pos, end_pos)
            if first_gap != -1 and first_gap > h_pos:
                spans = []
                curr = h_pos
                while curr < end_pos:
                    gap_idx = data.find(null_marker, curr, end_pos)
                    if gap_idx == -1:
                        spans.append((curr, end_pos))
                        break
                    if gap_idx > curr:
                        spans.append((curr, gap_idx))
                    skip = gap_idx
                    while skip < end_pos and data[skip:skip + 1] == b"\x00":
                        skip += 1
                    curr = skip

                candidates = []
                group_id = f"cand_{h_pos:08x}"
                for i, (st, en) in enumerate(spans):
                    is_first = (i == 0)
                    is_last = (i == len(spans) - 1)
                    m = {
                        "signature": sig.header.hex() if is_first else "",
                        "footer_signature": sig.footer.hex() if is_last else "",
                        "detection_method": "magic_bytes_disrupted" if not is_first else "magic_bytes",
                        "has_footer": is_last,
                        "group_id": group_id,
                    }
                    candidates.append({
                        "offset": st,
                        "length": en - st,
                        "type_hint": sig.type_hint,
                        "header_flag": is_first,
                        "footer_flag": is_last,
                        "metadata": m,
                    })
                return candidates

            # Contiguous candidate
            length = end_pos - h_pos
            meta["footer_signature"] = sig.footer.hex()
            meta["has_footer"] = True
            return [{
                "offset": h_pos,
                "length": length,
                "type_hint": sig.type_hint,
                "header_flag": True,
                "footer_flag": True,
                "metadata": meta,
            }]

    # Footer not found: carve as candidate fragment with bounded length
    length = min(sig.default_length, total_size - h_pos)
    meta["has_footer"] = False
    return [{
        "offset": h_pos,
        "length": length,
        "type_hint": sig.type_hint,
        "header_flag": True,
        "footer_flag": False,
        "metadata": meta,
    }]

def _determine_fragment_boundary(
    data: Union[bytes, mmap.mmap],
    sig: SignatureDefinition,
    h_pos: int,
    total_size: int,
) -> tuple[int, bool, Dict[str, Any]]:
    """
    Backward-compatible single-fragment boundary determination.
    """
    cands = _carve_candidates_for_header(data, sig, h_pos, total_size)
    first = cands[0]
    return first["length"], first["footer_flag"], first["metadata"]

def carve_fragments(evidence_path: Union[str, Path]) -> List[Fragment]:
    """
    Perform byte-level carving on an evidence disk/memory image.
    
    Scans the evidence file for supported magic bytes (JPEG, PDF, ZIP, SQLite),
    determines candidate fragment boundaries, and generates deterministic Fragment objects.
    
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

                # Scan for standalone continuation footers not covered by existing header candidates
                for sig in SIGNATURE_REGISTRY:
                    if sig.footer is not None:
                        f_search = 0
                        while f_search < file_size:
                            f_pos = mm.find(sig.footer, f_search)
                            if f_pos == -1:
                                break
                            
                            covered = any(c["offset"] <= f_pos < (c["offset"] + c["length"]) for c in candidates)
                            if not covered:
                                backtrack_limit = max(0, f_pos - sig.default_length)
                                start_cand = backtrack_limit
                                sub_bytes = mm[backtrack_limit:f_pos]
                                last_null_run = sub_bytes.rfind(b"\x00" * 32)
                                if last_null_run != -1:
                                    start_cand = backtrack_limit + last_null_run + 32
                                    while start_cand < f_pos and mm[start_cand:start_cand + 1] == b"\x00":
                                        start_cand += 1
                                
                                f_end = f_pos + len(sig.footer)
                                if sig.type_hint == "pdf":
                                    while f_end < file_size and mm[f_end:f_end + 1] in (b"\r", b"\n"):
                                        f_end += 1
                                
                                cand_len = f_end - start_cand
                                if cand_len >= 16:
                                    candidates.append({
                                        "offset": start_cand,
                                        "length": cand_len,
                                        "type_hint": sig.type_hint,
                                        "header_flag": False,
                                        "footer_flag": True,
                                        "metadata": {
                                            "signature": "",
                                            "footer_signature": sig.footer.hex(),
                                            "detection_method": "continuation_carving",
                                            "has_footer": True,
                                        },
                                    })
                            f_search = f_pos + len(sig.footer)

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

            for sig in SIGNATURE_REGISTRY:
                if sig.footer is not None:
                    f_search = 0
                    while f_search < file_size:
                        f_pos = data.find(sig.footer, f_search)
                        if f_pos == -1:
                            break
                        
                        covered = any(c["offset"] <= f_pos < (c["offset"] + c["length"]) for c in candidates)
                        if not covered:
                            backtrack_limit = max(0, f_pos - sig.default_length)
                            start_cand = backtrack_limit
                            sub_bytes = data[backtrack_limit:f_pos]
                            last_null_run = sub_bytes.rfind(b"\x00" * 32)
                            if last_null_run != -1:
                                start_cand = backtrack_limit + last_null_run + 32
                                while start_cand < f_pos and data[start_cand:start_cand + 1] == b"\x00":
                                    start_cand += 1
                            
                            f_end = f_pos + len(sig.footer)
                            if sig.type_hint == "pdf":
                                while f_end < file_size and data[f_end:f_end + 1] in (b"\r", b"\n"):
                                    f_end += 1
                            
                            cand_len = f_end - start_cand
                            if cand_len >= 16:
                                candidates.append({
                                    "offset": start_cand,
                                    "length": cand_len,
                                    "type_hint": sig.type_hint,
                                    "header_flag": False,
                                    "footer_flag": True,
                                    "metadata": {
                                        "signature": "",
                                        "footer_signature": sig.footer.hex(),
                                        "detection_method": "continuation_carving",
                                        "has_footer": True,
                                    },
                                })
                        f_search = f_pos + len(sig.footer)

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
            entropy=0.0,  # Unset placeholder, real entropy calculated in later stage
            source=source_str,
            pipeline_tag="carved",
            header_flag=cand["header_flag"],
            footer_flag=cand["footer_flag"],
            metadata=frag_meta,
        )
        fragments.append(fragment)

    return fragments
