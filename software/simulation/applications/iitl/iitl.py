import numpy as np
from extensions.simulation.src.utils import lib_control


class IITL:
    N: int  # Number of samples
    j: int
    t: np.ndarray  # Estimated transfer vector
    F_target: np.ndarray

    q: float
    s: float

    def __init__(self, N, F_target, q=0, s=1, t_0=None):

        self.N = N
        self.F_target = F_target
        self.q = q
        self.s = s

        if t_0 is None:
            self.t = np.zeros(N)
        else:
            self.t = t_0

        self.j = 0

    def update(self, y_source, y_target, u_source, u_target):

        # Calculate the error
        e_j = y_source - y_target

        # Calculate the optimal learning matrix
        s = self.s

        L_j = calculate_learning_matrix(self.F_target, u_source, q=self.q, s=s)

        t_new = self.t + L_j @ e_j

        self.t = t_new
        self.j += 1

        return self.t


def calculate_optimal_s(F_target, u_ref, s):
    s_optimal = np.linalg.norm(F_target @ lift(u_ref)) * s
    return s_optimal


def calculate_learning_matrix(F_target, u_ref, q, s):
    A = F_target @ lift(u_ref)

    Qw = q * np.eye(A.shape[0])
    Sw = s * np.eye(A.shape[0])

    L = np.linalg.inv(A.T @ Qw @ A + Sw) @ A.T @ Qw

    return L


def lift(v: np.ndarray) -> np.ndarray:
    """
    Lift operator: Create a lower-triangular Toeplitz matrix from a vector.

    Given a vector v = [v0, v1, ..., v_{n-1}], the matrix T is defined as:

        T[i, j] = v[i - j] for i >= j, and 0 otherwise.

    Parameters:
        v (np.ndarray): A 1D array of length n.

    Returns:
        np.ndarray: An n x n lower-triangular Toeplitz matrix.
    """
    n = len(v)
    i, j = np.indices((n, n))
    # For indices where i < j, set the value to 0
    T = np.where(i >= j, v[i - j], 0)
    return T


def inverse_lift(M: np.ndarray) -> np.ndarray:
    """
    Inverse lift operator: Extract the first column of a lower-triangular Toeplitz matrix.

    This assumes that M is a square matrix constructed with the lift function.

    Parameters:
        M (np.ndarray): A lower-triangular Toeplitz matrix (n x n).

    Returns:
        np.ndarray: A 1D array corresponding to the first column of M.
    """
    if M.shape[0] != M.shape[1]:
        raise ValueError("The input must be a square matrix.")
    return M[:, 0]
