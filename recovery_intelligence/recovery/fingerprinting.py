import math
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

from config import settings
from models.fragment import Fragment
from models.feature_vector import FeatureVector

# Global lazy holder for SentenceTransformer model
_SENTENCE_TRANSFORMER_MODEL = None
_SENTENCE_TRANSFORMER_LOAD_ATTEMPTED = False


def get_sentence_transformer():
    """Lazily load SentenceTransformer model if available."""
    global _SENTENCE_TRANSFORMER_MODEL, _SENTENCE_TRANSFORMER_LOAD_ATTEMPTED
    if not _SENTENCE_TRANSFORMER_LOAD_ATTEMPTED:
        _SENTENCE_TRANSFORMER_LOAD_ATTEMPTED = True
        try:
            from sentence_transformers import SentenceTransformer
            _SENTENCE_TRANSFORMER_MODEL = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)
        except Exception:
            _SENTENCE_TRANSFORMER_MODEL = None
    return _SENTENCE_TRANSFORMER_MODEL


def normalize_vector(vector: List[float]) -> List[float]:
    """
    Normalize vector to unit length (L2 norm).
    Handles zero vectors and non-finite values safely without producing NaN or Infinity.
    """
    if not vector:
        return [0.0] * settings.FINGERPRINT_DIMENSION

    arr = np.array(vector, dtype=np.float64)
    arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)

    norm = float(np.linalg.norm(arr))
    if norm == 0.0 or math.isnan(norm) or math.isinf(norm):
        dim = len(vector) if len(vector) > 0 else settings.FINGERPRINT_DIMENSION
        return [0.0] * dim

    normalized = (arr / norm).tolist()
    return [round(float(x), 6) for x in normalized]


def _extract_2gram_counts(data: bytes) -> Dict[int, int]:
    """Extract adjacent byte 2-gram frequencies from raw byte sequence."""
    counts: Dict[int, int] = {}
    if len(data) < 2:
        return counts
    for i in range(len(data) - 1):
        pair_code = (data[i] << 8) | data[i + 1]
        counts[pair_code] = counts.get(pair_code, 0) + 1
    return counts


def _batch_fingerprint_binary(data_list: List[bytes], ids: List[str]) -> List[FeatureVector]:
    """Generate 64-dimensional normalized feature vectors for a batch of binary fragments."""
    target_dim = settings.FINGERPRINT_DIMENSION
    n_samples = len(data_list)

    if n_samples == 0:
        return []

    sample_counts = [_extract_2gram_counts(d) for d in data_list]
    vocab = sorted(list(set(k for counts in sample_counts for k in counts.keys())))

    if not vocab or all(len(c) == 0 for c in sample_counts):
        return [
            FeatureVector(
                fragment_id=fid,
                vector=[0.0] * target_dim,
                dimension=target_dim,
                metadata={"fingerprint_method": "binary_2gram_tfidf_svd", "norm": 0.0},
            )
            for fid in ids
        ]

    vocab_idx = {gram: i for i, gram in enumerate(vocab)}
    n_vocab = len(vocab)

    tf_matrix = np.zeros((n_samples, n_vocab), dtype=np.float64)
    doc_freq = np.zeros(n_vocab, dtype=np.float64)

    for i, counts in enumerate(sample_counts):
        total_grams = sum(counts.values())
        if total_grams > 0:
            for gram, cnt in counts.items():
                col = vocab_idx[gram]
                tf_matrix[i, col] = cnt / float(total_grams)
                doc_freq[col] += 1.0

    idf = np.log((n_samples + 1.0) / (doc_freq + 1.0)) + 1.0
    tfidf_matrix = tf_matrix * idf

    k = min(target_dim, n_samples, n_vocab)
    if k > 0:
        try:
            u, s, vt = np.linalg.svd(tfidf_matrix, full_matrices=False)
            reduced = u[:, :k] * s[:k]
        except Exception:
            reduced = tfidf_matrix[:, :k]
    else:
        reduced = np.zeros((n_samples, 0), dtype=np.float64)

    results: List[FeatureVector] = []
    for i, fid in enumerate(ids):
        row = reduced[i].tolist() if reduced.shape[1] > 0 else []
        if len(row) < target_dim:
            row.extend([0.0] * (target_dim - len(row)))
        else:
            row = row[:target_dim]

        norm_vec = normalize_vector(row)
        norm_val = round(float(np.linalg.norm(norm_vec)), 4)

        results.append(
            FeatureVector(
                fragment_id=fid,
                vector=norm_vec,
                dimension=target_dim,
                metadata={
                    "fingerprint_method": "binary_2gram_tfidf_svd",
                    "norm": norm_val,
                },
            )
        )

    return results


def fingerprint_binary_fragment(data: bytes, fragment_id: str = "binary_fragment") -> FeatureVector:
    """Generate 64-dimensional feature vector for a single binary block."""
    vectors = _batch_fingerprint_binary([data], [fragment_id])
    return vectors[0]


def _text_tfidf_fallback(text: str) -> List[float]:
    """Deterministic TF-IDF fallback for text fragments when sentence-transformers is unavailable."""
    target_dim = settings.FINGERPRINT_DIMENSION

    words = [w.lower() for w in text.split() if w.strip()]
    chars = [text[i:i+3].lower() for i in range(len(text) - 2)]

    tokens = words + chars
    if not tokens:
        return [0.0] * target_dim

    from collections import Counter
    counts = Counter(tokens)
    vec = [0.0] * target_dim
    for token, count in counts.items():
        # Deterministic FNV-1a32 hash (process-independent, no PYTHONHASHSEED dependence)
        h = 2166136261
        for ch in token.encode("utf-8", errors="replace"):
            h = ((h ^ ch) * 16777619) & 0xFFFFFFFF
        bucket = h % target_dim
        vec[bucket] += float(count)

    return vec


def fingerprint_text_fragment(text: str, fragment_id: str = "text_fragment") -> FeatureVector:
    """Generate 64-dimensional feature vector for text data."""
    target_dim = settings.FINGERPRINT_DIMENSION

    if not text.strip():
        return FeatureVector(
            fragment_id=fragment_id,
            vector=[0.0] * target_dim,
            dimension=target_dim,
            metadata={"fingerprint_method": "text_tfidf_fallback", "norm": 0.0},
        )

    model = get_sentence_transformer()

    if model is not None:
        try:
            raw_emb = model.encode(text, convert_to_numpy=True)
            emb_list = raw_emb.tolist()
            if len(emb_list) > target_dim:
                emb_list = emb_list[:target_dim]
            elif len(emb_list) < target_dim:
                emb_list.extend([0.0] * (target_dim - len(emb_list)))

            norm_vec = normalize_vector(emb_list)
            return FeatureVector(
                fragment_id=fragment_id,
                vector=norm_vec,
                dimension=target_dim,
                metadata={
                    "fingerprint_method": "text_minilm_embedding",
                    "norm": round(float(np.linalg.norm(norm_vec)), 4),
                },
            )
        except Exception:
            pass

    fallback_vec = _text_tfidf_fallback(text)
    norm_vec = normalize_vector(fallback_vec)
    return FeatureVector(
        fragment_id=fragment_id,
        vector=norm_vec,
        dimension=target_dim,
        metadata={
            "fingerprint_method": "text_tfidf_fallback",
            "norm": round(float(np.linalg.norm(norm_vec)), 4),
        },
    )


def read_fragment_bytes(fragment: Fragment) -> bytes:
    """Read fragment bytes from source file in read-only mode."""
    source_path = Path(fragment.source)
    if not source_path.is_file():
        return b""
    with open(source_path, "rb") as f:
        f.seek(fragment.offset)
        return f.read(fragment.length)


def fingerprint_fragment(fragment: Fragment, data: Optional[bytes] = None) -> FeatureVector:
    """Generate a FeatureVector for a single Fragment based on its Stage 2 characterization."""
    raw_bytes = data if data is not None else read_fragment_bytes(fragment)
    char = fragment.metadata.get("characterization", "binary")

    if char == "text":
        try:
            text_str = raw_bytes.decode("utf-8", errors="ignore")
        except Exception:
            text_str = ""
        return fingerprint_text_fragment(text_str, fragment_id=fragment.id)
    else:
        # Mixed and binary fragments follow binary 2-gram path
        return fingerprint_binary_fragment(raw_bytes, fragment_id=fragment.id)


def fit_and_fingerprint(fragments: List[Fragment]) -> List[FeatureVector]:
    """
    Batch API to process a list of characterized fragments and return FeatureVector objects.
    
    Routes text fragments to text embedding/fallback, and binary/mixed fragments to batch 2-gram TF-IDF SVD.
    """
    if not fragments:
        return []

    text_frags: List[Tuple[Fragment, bytes]] = []
    binary_frags: List[Tuple[Fragment, bytes]] = []

    for f in fragments:
        raw_bytes = read_fragment_bytes(f)
        char = f.metadata.get("characterization", "binary")
        if char == "text":
            text_frags.append((f, raw_bytes))
        else:
            binary_frags.append((f, raw_bytes))

    results_map: Dict[str, FeatureVector] = {}

    for f, raw_b in text_frags:
        try:
            text_str = raw_b.decode("utf-8", errors="ignore")
        except Exception:
            text_str = ""
        results_map[f.id] = fingerprint_text_fragment(text_str, fragment_id=f.id)

    if binary_frags:
        b_datas = [b for _, b in binary_frags]
        b_ids = [f.id for f, _ in binary_frags]
        b_vecs = _batch_fingerprint_binary(b_datas, b_ids)
        for fv in b_vecs:
            results_map[fv.fragment_id] = fv

    return [results_map[f.id] for f in fragments if f.id in results_map]