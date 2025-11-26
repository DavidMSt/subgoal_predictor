from __future__ import annotations

import abc
import dataclasses
import enum
import numpy as np
import qmt

from core.utils.logging_utils import Logger

INDEX_X = 0
INDEX_Y = 1
INDEX_PSI = 2

INDEX_SIN = 2
INDEX_COS = 3


# === UTILITIES ========================================================================================================
def unscented_transform_psi_to_sin_cos(mean_psi: float, var_psi: float):
    """
    Applies the unscented transform to compute the mean and covariance of [sin(ψ), cos(ψ)]
    from the mean and variance of ψ.
    """

    # UT parameters
    n = 1  # dimension of ψ
    alpha = 1e-3
    beta = 2.0
    kappa = 0.0
    lambda_ = alpha ** 2 * (n + kappa) - n

    # Weights
    wm = np.zeros(2 * n + 1)
    wc = np.zeros(2 * n + 1)
    wm[0] = lambda_ / (n + lambda_)
    wc[0] = lambda_ / (n + lambda_) + (1 - alpha ** 2 + beta)
    for i in range(1, 2 * n + 1):
        wm[i] = wc[i] = 1.0 / (2 * (n + lambda_))

    # Sigma points for ψ
    sqrt_c = np.sqrt((n + lambda_) * var_psi)
    sigma_points = np.array([
        mean_psi,
        mean_psi + sqrt_c,
        mean_psi - sqrt_c
    ])

    # Transform to [sin(ψ), cos(ψ)]
    transformed = np.array([[np.sin(psi), np.cos(psi)] for psi in sigma_points])  # shape (3, 2)

    # Mean
    mean_trans = np.sum(wm[:, np.newaxis] * transformed, axis=0)

    # Covariance
    diff = transformed - mean_trans
    cov_trans = sum(wc[i] * np.outer(diff[i], diff[i]) for i in range(2 * n + 1))

    return mean_trans, cov_trans


# ----------------------------------------------------------------------------------------------------------------------
def get_rotation_matrix(psi: float):
    R = np.array([
        [np.cos(psi), -np.sin(psi), 0, ],
        [np.sin(psi), np.cos(psi), 0, ],
        [0, 0, 1, ],
    ])
    return R


# ----------------------------------------------------------------------------------------------------------------------
def dR_dpsi_times_vec(psi: float, z: np.ndarray) -> np.ndarray:
    """
    Compute (d/dpsi) [ R(psi) * z ] for 3x1 z = [z_x, z_y, z_psi].
    Only x,y depend on psi; psi row is zero. For 2x2 R(psi) = [[c,-s],[s,c]]:
      dR/dpsi = [[-s, -c],
                 [ c, -s]]
    """
    c, s = np.cos(psi), np.sin(psi)
    J2 = np.array([[-s, -c],
                   [c, -s]])
    xy = J2 @ z[:2]
    out = np.array([xy[0], xy[1], 0.0])
    return out


# ----------------------------------------------------------------------------------------------------------------------
def get_covariance_ellipse(P_xy) -> tuple[float, float, float]:
    # Numerical hygiene: symmetrize and clip tiny negatives
    P_xy = 0.5 * (P_xy + P_xy.T)
    eigvals, eigvecs = np.linalg.eigh(P_xy)  # eigh for symmetric
    order = np.argsort(eigvals)[::-1]  # sort: λ_max first
    eigvals = eigvals[order]
    eigvecs = eigvecs[:, order]
    eigvals = np.maximum(eigvals, 0.0)
    # Choose confidence: 95% for 2 DoF → chi2 = 5.991
    # (68%: 2.279, 95%: 5.991, 99%: 9.210)
    chi2 = 1
    # chi2 = 1

    # Semi-axes (meters). NOTE: rx, ry are *radii* of the ellipse, not diameters.
    rx = float(np.sqrt(chi2 * eigvals[0]))  # major
    ry = float(np.sqrt(chi2 * eigvals[1]))  # minor

    # Orientation of major axis in global frame
    psi_ellipse = float(np.arctan2(eigvecs[1, 0], eigvecs[0, 0]))

    return rx, ry, psi_ellipse


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass
class AlgorithmAgentState:
    x: float = 0.0
    y: float = 0.0
    psi: float = 0.0

    def as_array(self):
        return np.array([self.x, self.y, self.psi])

    @staticmethod
    def from_array(array):
        return AlgorithmAgentState(array[0], array[1], array[2])


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass
class AlgorithmAgentInput:
    v: float = 0.0
    psi_dot: float = 0.0

    def as_array(self):
        return np.array([self.v, self.psi_dot])

    @classmethod
    def from_array(cls, array):
        new_input = cls()
        new_input.v = array[0]
        new_input.psi_dot = array[1]
        return new_input


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(frozen=True)
class AlgorithmAgentMeasurement:
    agent_from: str
    agent_to: str
    measurement: np.ndarray
    covariance: np.ndarray


# ----------------------------------------------------------------------------------------------------------------------
def augment_measurement(measurement: AlgorithmAgentMeasurement) -> np.ndarray:
    return np.array([
        measurement.measurement[0],
        measurement.measurement[1],
        np.sin(measurement.measurement[2]),
        np.cos(measurement.measurement[2]),
    ])


# ----------------------------------------------------------------------------------------------------------------------
def augment_measurement_covariance(measurement: AlgorithmAgentMeasurement) -> np.ndarray:
    P = measurement.covariance
    psi_hat = float(measurement.measurement[2])
    var_psi = float(P[2, 2])

    _, cov_sin_cos = unscented_transform_psi_to_sin_cos(psi_hat, var_psi)

    # Build full 4x4 augmented covariance matrix
    P_aug = np.zeros((4, 4))
    P_aug[0, 0] = P[0, 0]
    P_aug[1, 1] = P[1, 1]
    P_aug[2:4, 2:4] = cov_sin_cos

    return P_aug


# ----------------------------------------------------------------------------------------------------------------------
def augment_state(state: AlgorithmAgentState) -> np.ndarray:
    return np.array([
        state.x,
        state.y,
        np.sin(state.psi),
        np.cos(state.psi),
    ])


# ----------------------------------------------------------------------------------------------------------------------
def augment_state_array(state: np.ndarray) -> np.ndarray:
    return np.array([
        state[0],
        state[1],
        np.sin(state[2]),
        np.cos(state[2]),
    ])


# ----------------------------------------------------------------------------------------------------------------------
def augment_covariance(covariance: np.ndarray, psi: float) -> np.ndarray:
    # First-order Jacobian
    J = np.array([
        [1, 0, 0],
        [0, 1, 0],
        [0, 0, np.cos(psi)],
        [0, 0, -np.sin(psi)]
    ])

    # Initial linearized covariance
    P_aug = J @ covariance @ J.T

    # Second-order corrections for sin(psi) and cos(psi)
    sin_psi = np.sin(psi)
    cos_psi = np.cos(psi)

    var_psi = covariance[INDEX_PSI, INDEX_PSI]
    var_sin = (cos_psi ** 2) * var_psi + 0.5 * (sin_psi ** 2) * (var_psi ** 2)
    var_cos = (sin_psi ** 2) * var_psi + 0.5 * (cos_psi ** 2) * (var_psi ** 2)

    # Optional: Covariance between sin and cos (can be helpful if needed)
    cov_sin_cos = -sin_psi * cos_psi * var_psi \
                  + 0.5 * sin_psi * cos_psi * (cos_psi ** 2 - sin_psi ** 2) * (var_psi ** 2)

    # Apply the corrections
    P_aug[2, 2] = var_sin
    P_aug[3, 3] = var_cos
    P_aug[2, 3] = cov_sin_cos
    P_aug[3, 2] = cov_sin_cos  # symmetric

    return P_aug


# ----------------------------------------------------------------------------------------------------------------------
def get_state_from_augmented(augmented_state: np.ndarray) -> AlgorithmAgentState:
    return AlgorithmAgentState(
        x=float(augmented_state[0]),
        y=float(augmented_state[1]),
        psi=float(np.arctan2(augmented_state[INDEX_SIN], augmented_state[INDEX_COS]))
    )


# ----------------------------------------------------------------------------------------------------------------------
def get_covariance_from_augmented(augmented_covariance: np.ndarray, psi: float) -> np.ndarray:
    s = np.sin(psi)
    c = np.cos(psi)
    r2 = s * s + c * c

    s, c = np.sin(psi), np.cos(psi)
    r2 = max(s * s + c * c, 1e-8)  # <- guard

    J = np.array([
        [1, 0, 0, 0],
        [0, 1, 0, 0],
        [0, 0, c / r2, -s / r2],
    ])

    covariance = J @ augmented_covariance @ J.T
    return covariance


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass
class AlgorithmAgentSettings:
    sigma_v: float = 0.005
    sigma_w: float = 0.002
    k_v: float = 1
    k_w: float = 0.6

    static_noise_floor: float = 1e-3  # per second


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass
class AlgorithmAgent:
    id: str
    Ts: float
    state: AlgorithmAgentState
    covariance: np.ndarray
    settings: AlgorithmAgentSettings = dataclasses.field(default_factory=AlgorithmAgentSettings)
    is_anchor: bool = False
    input: AlgorithmAgentInput = dataclasses.field(default_factory=AlgorithmAgentInput)
    measurements: list[AlgorithmAgentMeasurement] = dataclasses.field(default_factory=list)

    # ------------------------------------------------------------------------------------------------------------------
    def input_covariance_from_input(self, u: AlgorithmAgentInput, is_anchor: bool = False):
        if is_anchor:
            # Anchors: no input-driven process noise at all
            return np.zeros((2, 2))

        v = abs(u.v)
        w = abs(u.psi_dot)

        std_v = self.settings.sigma_v + self.settings.k_v * v
        std_w = self.settings.sigma_w + self.settings.k_w * w

        return np.diag([std_v ** 2, std_w ** 2])

    # ------------------------------------------------------------------------------------------------------------------
    def get_covariance_norm(self, order=None):
        return np.linalg.norm(self.covariance, order)


# ----------------------------------------------------------------------------------------------------------------------
class LocalizationAlgorithm(abc.ABC):
    agents: dict[str, AlgorithmAgent]
    Ts: float
    step: int = 0

    def __init__(self, Ts: float):
        self.Ts = Ts
        self.logger = Logger('LocalizationAlgorithm', 'DEBUG')

    @abc.abstractmethod
    def initialize(self, agents: list[AlgorithmAgent]):
        ...

    @abc.abstractmethod
    def prediction(self):
        ...

    @abc.abstractmethod
    def correction(self):
        ...
