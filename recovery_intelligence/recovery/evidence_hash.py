import hashlib
from pathlib import Path
from typing import Union
from datetime import datetime, timezone
from models.evidence import Evidence

CHUNK_SIZE = 64 * 1024  # 64 KB chunks for safe memory usage

def validate_evidence_file(file_path: Union[str, Path]) -> Path:
    """
    Validate that the evidence file exists, is a regular file, is readable, and not empty.
    
    Raises:
        ValueError: If file_path is empty, not a regular file, or empty (0 bytes).
        FileNotFoundError: If the file does not exist.
        PermissionError: If the file cannot be accessed.
    """
    if not file_path:
        raise ValueError("Evidence file path must not be empty.")

    path = Path(file_path).resolve()

    if not path.exists():
        raise FileNotFoundError(f"Evidence file does not exist: {path}")

    if not path.is_file():
        raise ValueError(f"Evidence path is not a regular file: {path}")

    stat = path.stat()
    if stat.st_size == 0:
        raise ValueError(f"Evidence file is empty (0 bytes): {path}")

    # Check readability by opening in binary mode
    try:
        with open(path, "rb") as f:
            f.read(1)
    except PermissionError as e:
        raise PermissionError(f"Permission denied reading evidence file: {path}") from e
    except OSError as e:
        raise OSError(f"Unable to read evidence file: {path} ({e})") from e

    return path

def calculate_sha256(file_path: Union[str, Path]) -> str:
    """
    Calculate the SHA-256 hash of an evidence file incrementally.
    
    Reads in 64 KB chunks to handle arbitrarily large storage images without
    loading the full file into memory.
    
    Returns:
        Lowercase hexadecimal SHA-256 string.
    """
    path = validate_evidence_file(file_path)
    hasher = hashlib.sha256()

    with open(path, "rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            hasher.update(chunk)

    return hasher.hexdigest().lower()

def create_evidence_record(file_path: Union[str, Path]) -> Evidence:
    """
    Create an Evidence model record with SHA-256 hash and file metadata.
    """
    path = validate_evidence_file(file_path)
    sha256_hash = calculate_sha256(path)
    stat = path.stat()

    return Evidence(
        evidence_id=f"EV-{sha256_hash[:12].upper()}",
        source_path=str(path),
        sha256=sha256_hash,
        created_at=datetime.now(timezone.utc).isoformat(),
        metadata={
            "file_name": path.name,
            "size_bytes": stat.st_size,
        },
    )
