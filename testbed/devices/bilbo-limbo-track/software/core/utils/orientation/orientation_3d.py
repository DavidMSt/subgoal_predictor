import numpy as np
import qmt

def transform_vector_from_a_to_b_frame(vector_in_a_frame, orientation_from_b_to_a):
    return qmt.rotate(orientation_from_b_to_a, vector_in_a_frame)

def vector_from_local_to_global(vector_in_local_frame: np.ndarray, local_orientation: np.ndarray):
    return qmt.rotate(local_orientation, vector_in_local_frame)

def vector_from_global_to_local(vector_in_global_frame: np.ndarray, target_frame_global_orientation: np.ndarray):
    return qmt.rotate(qmt.qinv(target_frame_global_orientation), vector_in_global_frame)

def calculate_intersection(line1_start, line1_end, line2_start, line2_end):
    """
    Compute the closest point between two (possibly skew) 3D lines given by
    line1_start -> line1_end and line2_start -> line2_end.

    The function treats the inputs as infinite lines (not finite segments).
    It returns the midpoint between the two closest points on each line,
    which is commonly used as the 'best intersection' for noisy data.

    Parameters
    ----------
    line1_start, line1_end : np.ndarray, shape (3,)
    line2_start, line2_end : np.ndarray, shape (3,)

    Returns
    -------
    intersection_point : np.ndarray, shape (3,)
        The midpoint between the closest points on the two lines.
    """
    p1 = np.asarray(line1_start, dtype=float)
    p2 = np.asarray(line1_end, dtype=float)
    p3 = np.asarray(line2_start, dtype=float)
    p4 = np.asarray(line2_end, dtype=float)

    # Direction vectors of the lines
    u = p2 - p1
    v = p4 - p3
    w0 = p1 - p3

    a = np.dot(u, u)       # always >= 0
    b = np.dot(u, v)
    c = np.dot(v, v)       # always >= 0
    d = np.dot(u, w0)
    e = np.dot(v, w0)

    denom = a * c - b * b  # denominator for the parameters

    # If denom is very small, lines are almost parallel
    if np.isclose(denom, 0.0):
        # Take one point on line1 (p1) and project it onto line2
        if np.isclose(c, 0.0):
            # Degenerate case: line2_start == line2_end
            closest_point_line1 = p1
            closest_point_line2 = p3
        else:
            t = -e / c
            closest_point_line1 = p1
            closest_point_line2 = p3 + t * v
    else:
        s = (b * e - c * d) / denom
        t = (a * e - b * d) / denom

        closest_point_line1 = p1 + s * u
        closest_point_line2 = p3 + t * v

    # Midpoint between the two closest points
    intersection_point = 0.5 * (closest_point_line1 + closest_point_line2)
    return intersection_point