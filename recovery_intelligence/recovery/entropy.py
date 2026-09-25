import math
from collections import Counter
from pathlib import Path
from typing import List, Dict, Any, Optional

from config import settings
from models.fragment import Fragment

# Common printable ASCII bytes (32 to 126 inclusive) + whitespace (\t, \n, \r)
PRINTABLE_BYTES: set[int] = set(range(32, 127)) | {9, 10, 13}

def calculate_entropy(data: bytes) -> float:
    """
    Calculate Shannon entropy of a byte sequence in bits per byte (0.0 to 8.0).
    
    Formula:
        H(X) = - sum(p_i * log2(p_i))
        
    Edge Cases:
        - Empty sequence (0 bytes): Returns 0.0 (contains no information).
        - Uniform/repeated bytes (e.g. all 0x00 or all 'A'): Returns 0.0.
        - 256 uniformly distributed bytes: Returns 8.0.
        
    Returns:
        Deterministic float rounded to 4 decimal places in range [0.0, 8.0].
    """
    total_bytes = len(data)
    if total_bytes == 0:
        return 0.0

    counts = Counter(data)
    entropy = 0.0

    for count in counts.values():
        probability = count / total_bytes
        entropy -= probability * math.log2(probability)

    # Bound to strictly 0.0 - 8.0 range and round for deterministic precision
    entropy = max(0.0, min(8.0, entropy))
    return round(entropy, 4)

def calculate_printable_ratio(data: bytes) -> float:
    """
    Calculate the ratio of printable ASCII and standard whitespace characters.
    
    Returns:
        Float in range [0.0, 1.0].
    """
    if not data:
        return 0.0

    printable_count = sum(1 for b in data if b in PRINTABLE_BYTES)
    return round(printable_count / len(data), 4)

def analyze_entropy_windows(
    data: bytes,
    window_size: Optional[int] = None,
    step_size: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Perform sliding-window Shannon entropy analysis over a byte sequence.
    
    Args:
        data: Raw byte sequence to analyze.
        window_size: Number of bytes per sliding window (default from settings).
        step_size: Step increment to advance sliding window (default from settings).
        
    Returns:
        List of JSON-serializable window dictionaries:
        [{"start": int, "end": int, "offset": int, "length": int, "entropy": float}, ...]
    """
    total_len = len(data)
    if total_len == 0:
        return []

    w_size = window_size or settings.ENTROPY_WINDOW_SIZE
    s_size = step_size or settings.ENTROPY_STEP_SIZE

    # If data is smaller than or equal to window size, evaluate as single window
    if total_len <= w_size:
        return [{
            "start": 0,
            "end": total_len,
            "offset": 0,
            "length": total_len,
            "entropy": calculate_entropy(data),
        }]

    windows: List[Dict[str, Any]] = []
    start = 0

    while start < total_len:
        end = min(start + w_size, total_len)
        window_bytes = data[start:end]
        win_entropy = calculate_entropy(window_bytes)

        windows.append({
            "start": start,
            "end": end,
            "offset": start,
            "length": end - start,
            "entropy": win_entropy,
        })

        if end >= total_len:
            break
        start += s_size

    return windows

def determine_characterization(
    data: bytes,
    overall_entropy: float,
    printable_ratio: float,
    windows: List[Dict[str, Any]],
) -> str:
    """
    Characterize fragment content as 'text', 'binary', or 'mixed' based on deterministic heuristics.
    
    Rules:
        - MIXED: Sliding windows show statistically material divergence between high-entropy and low-entropy regions.
        - TEXT: Predominantly printable characters and low-to-medium entropy.
        - BINARY: High entropy, low printable ratio, or prevalent non-printable bytes.
    """
    if len(data) == 0:
        return "binary"

    # Check for mixed characteristics across sliding windows if multiple windows exist
    if len(windows) >= 2:
        entropies = [w["entropy"] for w in windows]
        delta = max(entropies) - min(entropies)
        
        # If one window is high entropy and another is low entropy, or significant divergence
        has_high_region = any(e >= settings.ENTROPY_BINARY_MIN for e in entropies)
        has_low_region = any(e <= settings.ENTROPY_TEXT_MAX for e in entropies)
        
        if delta >= settings.MIXED_ENTROPY_DELTA and (has_high_region and has_low_region):
            return "mixed"

    # Evaluate whole-fragment properties
    if printable_ratio >= settings.PRINTABLE_RATIO_TEXT_THRESHOLD and overall_entropy <= settings.ENTROPY_TEXT_MAX:
        return "text"

    if printable_ratio <= settings.PRINTABLE_RATIO_BINARY_THRESHOLD or overall_entropy >= settings.ENTROPY_BINARY_MIN:
        return "binary"

    # Secondary check for intermediate ratios
    if printable_ratio >= 0.70 and overall_entropy <= 6.0:
        return "text"

    return "binary"

def read_fragment_bytes(fragment: Fragment, max_bytes: Optional[int] = None) -> bytes:
    """
    Read real bytes belonging to a fragment from the source evidence image.
    
    Opens the evidence file strictly in read-only mode, seeks to fragment.offset,
    and reads only fragment.length bytes.
    """
    source_path = Path(fragment.source)
    if not source_path.is_file():
        raise FileNotFoundError(f"Source evidence file does not exist: {source_path}")

    read_len = fragment.length if max_bytes is None else min(fragment.length, max_bytes)

    with open(source_path, "rb") as f:
        f.seek(fragment.offset)
        return f.read(read_len)

def characterize_fragment(fragment: Fragment, data: Optional[bytes] = None) -> Fragment:
    """
    Perform complete Stage 2 characterization on a carved Fragment.
    
    Updates:
        - fragment.entropy with real Shannon entropy
        - fragment.pipeline_tag = "characterized"
        - fragment.metadata with characterization, printable_ratio, and sliding windows.
    """
    raw_data = data if data is not None else read_fragment_bytes(fragment)

    whole_entropy = calculate_entropy(raw_data)
    printable_ratio = calculate_printable_ratio(raw_data)
    windows = analyze_entropy_windows(
        raw_data,
        window_size=settings.ENTROPY_WINDOW_SIZE,
        step_size=settings.ENTROPY_STEP_SIZE,
    )
    characterization = determine_characterization(raw_data, whole_entropy, printable_ratio, windows)

    fragment.entropy = whole_entropy
    fragment.pipeline_tag = "characterized"
    fragment.metadata["characterization"] = characterization
    fragment.metadata["printable_ratio"] = printable_ratio
    fragment.metadata["entropy_window_size"] = settings.ENTROPY_WINDOW_SIZE
    fragment.metadata["entropy_step_size"] = settings.ENTROPY_STEP_SIZE
    fragment.metadata["entropy_windows"] = windows

    return fragment