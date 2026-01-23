import dataclasses

import numpy as np
from core.utils.orientation.orientation_2d import rotate_vector


def vector2GlobalFrame(vec: np.ndarray, psi: float):
    vec_out = rotate_vector(vec, psi)
    return vec_out


def vector2LocalFrame(vec: np.ndarray, psi: float):
    vec_out = rotate_vector(vec, -psi)
    return vec_out
