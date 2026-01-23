import math

import numpy as np

frodo_virtual_agent_colors = {
    'frodo1_v': [0.25, 0.4, 0.13],
    'frodo2_v': [0.62, 0.19, 0.74],
    'frodo3_v': [0.1, 0.6, 0.4],
    'frodo4_v': [0.7, 0.2, 0.1],
}


def is_view_obstructed(observer_pos: np.ndarray,
                       target_pos: np.ndarray,
                       obstacles: list[tuple[np.ndarray, float]],
                       epsilon: float = 1e-6) -> bool:
    """
    Determine whether the straight-line view from observer_pos to target_pos is obstructed
    by any circular obstacle (center, radius) in `obstacles`. Radii should already reflect
    object sizes (e.g., size/2 when size is a diameter).

    The check computes the minimum distance from each obstacle center to the segment,
    and flags an obstruction if that distance <= radius (with a tiny epsilon).
    """
    p = np.asarray(observer_pos, dtype=float).reshape(2)
    q = np.asarray(target_pos, dtype=float).reshape(2)
    seg = q - p
    seg_len2 = float(seg @ seg)
    if seg_len2 <= epsilon:
        # Degenerate segment; treat as unobstructed
        return False

    for c, r in obstacles:
        c = np.asarray(c, dtype=float).reshape(2)
        # Project center onto the segment, clamp t to [0,1]
        t = float(np.dot(c - p, seg) / seg_len2)
        t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
        proj = p + t * seg
        dist = np.linalg.norm(c - proj)
        if dist <= (r + epsilon):
            return True
    return False
