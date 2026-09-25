from collections import Counter
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

from config import settings
from models.fragment import Fragment
from models.feature_vector import FeatureVector
from models.cluster import FragmentCluster
from recovery.relationship_graph import calculate_cosine_similarity


def _run_dbscan(
    distance_matrix: np.ndarray,
    eps: float,
    min_samples: int,
) -> List[int]:
    """
    Deterministic DBSCAN clustering algorithm operating on a precomputed distance matrix.
    
    Returns:
        List of cluster labels for each sample (0, 1, 2, ... for clusters, -1 for noise/orphans).
    """
    n = distance_matrix.shape[0]
    labels = [-1] * n
    visited = [False] * n
    cluster_id = 0

    for i in range(n):
        if visited[i]:
            continue
        visited[i] = True

        # Find epsilon-neighbors of i
        neighbors = [j for j in range(n) if distance_matrix[i, j] <= eps]

        if len(neighbors) < min_samples:
            labels[i] = -1  # Noise / orphan candidate
        else:
            labels[i] = cluster_id
            # Expand cluster queue
            queue = [nb for nb in neighbors if nb != i]
            qi = 0
            while qi < len(queue):
                p = queue[qi]
                qi += 1

                if not visited[p]:
                    visited[p] = True
                    p_neighbors = [j for j in range(n) if distance_matrix[p, j] <= eps]
                    if len(p_neighbors) >= min_samples:
                        for p_nb in p_neighbors:
                            if p_nb not in queue and p_nb != i:
                                queue.append(p_nb)

                if labels[p] == -1:
                    labels[p] = cluster_id

            cluster_id += 1

    return labels


def cluster_fragments(
    features: List[FeatureVector],
    fragments: Optional[List[Fragment]] = None,
    eps: Optional[float] = None,
    min_samples: Optional[int] = None,
) -> Tuple[List[FragmentCluster], List[str]]:
    """
    Cluster fragment feature vectors using DBSCAN on cosine distance.
    
    Returns:
        (List[FragmentCluster], List[str] of orphan fragment IDs)
    """
    if not features:
        return [], []

    eps_val = float(eps) if eps is not None else float(settings.DBSCAN_EPS)
    min_samp = int(min_samples) if min_samples is not None else int(settings.DBSCAN_MIN_SAMPLES)

    n = len(features)
    frag_map: Dict[str, Fragment] = {f.id: f for f in fragments} if fragments else {}

    # Build NxN cosine distance matrix
    dist_matrix = np.zeros((n, n), dtype=np.float64)
    for i in range(n):
        for j in range(i + 1, n):
            sim = calculate_cosine_similarity(features[i].vector, features[j].vector)
            dist = max(0.0, 1.0 - max(0.0, sim))

            # Group linkage for disrupted file continuation fragments
            if fragments and features[i].fragment_id in frag_map and features[j].fragment_id in frag_map:
                fa = frag_map[features[i].fragment_id]
                fb = frag_map[features[j].fragment_id]
                grp_a = fa.metadata.get("group_id")
                grp_b = fb.metadata.get("group_id")
                if grp_a and grp_b and grp_a == grp_b:
                    dist = 0.05

            dist_matrix[i, j] = dist
            dist_matrix[j, i] = dist

    # Try scikit-learn DBSCAN if installed, otherwise use pure NumPy DBSCAN
    try:
        from sklearn.cluster import DBSCAN
        db = DBSCAN(eps=eps_val, min_samples=min_samp, metric="precomputed")
        labels = db.fit_predict(dist_matrix).tolist()
    except Exception:
        labels = _run_dbscan(dist_matrix, eps=eps_val, min_samples=min_samp)

    # Group members by cluster label
    clusters_dict: Dict[int, List[int]] = {}
    orphans: List[str] = []

    for idx, label in enumerate(labels):
        fid = features[idx].fragment_id
        if label == -1:
            orphans.append(fid)
        else:
            clusters_dict.setdefault(label, []).append(idx)

    result_clusters: List[FragmentCluster] = []

    for label in sorted(clusters_dict.keys()):
        member_indices = clusters_dict[label]
        member_fids = [features[i].fragment_id for i in member_indices]

        # Determine inferred type from member fragments
        member_types = []
        for fid in member_fids:
            if fid in frag_map:
                t = frag_map[fid].type_hint
                if t and t != "unknown":
                    member_types.append(t)

        if member_types:
            inferred_type = Counter(member_types).most_common(1)[0][0]
        else:
            inferred_type = "unknown"

        # Calculate cluster confidence (mean pairwise similarity)
        if len(member_indices) > 1:
            sims = []
            for a_i in range(len(member_indices)):
                for b_i in range(a_i + 1, len(member_indices)):
                    idx_a = member_indices[a_i]
                    idx_b = member_indices[b_i]
                    sims.append(calculate_cosine_similarity(features[idx_a].vector, features[idx_b].vector))
            avg_sim = float(np.mean(sims)) if sims else 0.5
        else:
            avg_sim = 0.5

        confidence = round(max(0.1, min(1.0, avg_sim)), 4)

        reason = (
            f"{len(member_fids)} fragments grouped (inferred type: '{inferred_type}') "
            f"with mean intra-cluster vector similarity of {confidence:.2f} (DBSCAN eps={eps_val:.2f})"
        )

        cluster_obj = FragmentCluster(
            cluster_id=f"cluster_{label:03d}",
            member_fragment_ids=member_fids,
            inferred_type=inferred_type,
            confidence=confidence,
            reason=reason,
        )
        result_clusters.append(cluster_obj)

    return result_clusters, orphans