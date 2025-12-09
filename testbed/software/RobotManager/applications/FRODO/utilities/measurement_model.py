from __future__ import annotations
import dataclasses
from dataclasses import dataclass, field, asdict
from typing import Literal, Optional

import numpy as np
import matplotlib.pyplot as plt
import yaml

from core.utils.files import fileExists, get_absolute_path


@dataclass
class ErrorModelSingleParam:
    """
    Very simple "knee" (piecewise-linear) standard-deviation model.

    std(value) =
        baseline + gain_1 * value                , if value < corner
        baseline + gain_1 * corner
                 + gain_2 * (value - corner)     , otherwise

    Notes:
    - You pass in a non-negative scalar "value" (we'll abs() it anyway).
    - For psi, v, and psi_dot we pass them in physical units (rad, m/s, rad/s).
    """
    baseline: float = 0.0  # unit of the target DOF (m for x/y, rad for psi)
    gain_1: float = 0.0  # same units as baseline per unit of "value"
    gain_2: float | None = None
    corner: float | None = None  # where the slope changes (same units as "value")

    def get_std(self, value: float) -> float:
        value = abs(float(value))

        if self.corner is None:
            return self.baseline + self.gain_1 * value

        if value < self.corner:
            return self.baseline + value * self.gain_1
        return self.baseline + self.corner * self.gain_1 + (value - self.corner) * self.gain_2


@dataclass
class ErrorModel:
    """
    Independent contributors combined in quadrature for a single DOF.
    - distance   : distance in m
    - bearing   : value in [0..1] (normalized |bearing| / (FOV/2))
    - psi       : radians
    - v         : m/s
    - psi_dot   : rad/s
    """
    distance: ErrorModelSingleParam = field(default_factory=ErrorModelSingleParam)
    bearing: ErrorModelSingleParam = field(default_factory=ErrorModelSingleParam)
    psi: ErrorModelSingleParam = field(default_factory=ErrorModelSingleParam)
    v: ErrorModelSingleParam = field(default_factory=ErrorModelSingleParam)
    psi_dot: ErrorModelSingleParam = field(default_factory=ErrorModelSingleParam)

    def get_std(self, distance: float, bearing: float, psi: float, v: float, psi_dot: float) -> float:
        return float(np.sqrt(
            self.distance.get_std(distance) ** 2 +
            self.bearing.get_std(bearing) ** 2 +
            self.psi.get_std(psi) ** 2 +
            self.v.get_std(v) ** 2 +
            self.psi_dot.get_std(psi_dot) ** 2
        ))


# ==============================
# Measurement Model
# ==============================

@dataclass
class CovarianceModel:
    """
    Measurement model for an ArUco detection in the camera frame.
    The measurement vector is [x, y, psi] with units [m, m, rad].

    Normalizations (kept very simple):
    - distance = clamp((d - d_min)/(d_max - d_min), 0..1)
      where bearing = atan2(y, x)

    Each output DOF (x, y, psi) has its own independent ErrorModel.
    """
    # Per-DOF independent models (units: x,y in meters; psi in radians)
    x: ErrorModel = field(default_factory=ErrorModel)
    y: ErrorModel = field(default_factory=ErrorModel)
    psi: ErrorModel = field(default_factory=ErrorModel)

    def covariance(self, measurement: np.ndarray, v: float, psi_dot: float) -> np.ndarray:
        """
        Returns a 3x3 diagonal covariance matrix diag([σ_x^2, σ_y^2, σ_psi^2]).
        """
        mx = float(measurement[0])
        my = float(measurement[1])
        mpsi = float(measurement[2])
        distance = float(np.hypot(mx, my))

        bearing = float(np.arctan2(my, mx))

        # Build component standard deviations (independent → quadrature)
        std_x = self.x.get_std(distance, bearing, mpsi, v, psi_dot)
        std_y = self.y.get_std(distance, bearing, mpsi, v, psi_dot)
        std_psi = self.psi.get_std(distance, bearing, mpsi, v, psi_dot)

        return np.diag([std_x ** 2, std_y ** 2, std_psi ** 2])


@dataclass
class FRODO_MeasurementModel:
    fov: float = 0.0
    min_measurement_distance: float = 0.0
    max_measurement_distance: float = 2.0
    bias_x: float = 0.0
    bias_y: float = 0.0
    bias_psi: float = 0.0
    covariance: CovarianceModel = field(default_factory=CovarianceModel)

    # ------------------------------------------------------------------------------------------------------------------
    def process_measurement(self, measurement: np.ndarray, v: float, psi_dot: float) -> tuple[
        bool, np.ndarray, np.ndarray]:
        """
        Takes a measurement vector and returns a validity flag and a processed measurement vector and covariance.

        Args:
            measurement: np.ndarray  Measurement vector [x, y, psi] in units [m, m, rad]

        Returns:
            tuple[bool, np.ndarray, np.ndarray]: (is_valid, processed_measurement, covariance)
        """
        # --- basic extraction & sanity checks ---
        if measurement is None or len(measurement) < 3:
            nan_vec = np.array([np.nan, np.nan, np.nan], dtype=float)
            return False, nan_vec, np.diag([np.nan, np.nan, np.nan])

        mx = float(measurement[0])
        my = float(measurement[1])
        mpsi = float(measurement[2])

        if not np.all(np.isfinite([mx, my, mpsi])):
            nan_vec = np.array([np.nan, np.nan, np.nan], dtype=float)
            return False, nan_vec, np.diag([np.nan, np.nan, np.nan])

        # --- debias measurement ---
        x = mx - self.bias_x
        y = my - self.bias_y
        psi = mpsi - self.bias_psi

        # wrap psi to [-pi, pi]
        psi = (psi + np.pi) % (2.0 * np.pi) - np.pi

        # --- validity checks (distance & FOV) ---
        distance = float(np.hypot(x, y))
        if distance < self.min_measurement_distance or distance > self.max_measurement_distance:
            nan_vec = np.array([np.nan, np.nan, np.nan], dtype=float)
            return False, nan_vec, np.diag([np.nan, np.nan, np.nan])

        if self.fov and self.fov > 0.0:
            bearing = float(np.arctan2(y, x))  # radians
            if abs(bearing) > (self.fov * 0.5):
                nan_vec = np.array([np.nan, np.nan, np.nan], dtype=float)
                return False, nan_vec, np.diag([np.nan, np.nan, np.nan])

        processed = np.array([x, y, psi], dtype=float)

        # --- covariance from processed measurement ---
        cov = self.get_covariance(processed, v, psi_dot)

        return True, processed, cov

    # ------------------------------------------------------------------------------------------------------------------
    def get_covariance(self, measurement: np.ndarray, v: float, psi_dot: float) -> np.ndarray:
        return self.covariance.covariance(measurement, v, psi_dot)

    # ------------------------------------------------------------------------------------------------------------------
    def __repr__(self):
        cov_repr = repr(self.covariance).replace("\n", "")
        return (
            f"{self.__class__.__name__}("
            f"fov={self.fov:.3f}, "
            f"min_d={self.min_measurement_distance:.1f}, "
            f"max_d={self.max_measurement_distance:.1f}, "
            f"bias_x={self.bias_x:.2f}, "
            f"bias_y={self.bias_y:.2f}, "
            f"bias_psi={self.bias_psi:.2f}, "
            f"covariance={cov_repr}"
            ")"
        )


# ==============================
# Thin wrappers (if you like)
# ==============================

def get_covariance(measurement: np.ndarray, v: float, psi_dot: float, model: CovarianceModel) -> np.ndarray:
    """
    Matches your function name/signature. Returns a 3x3 diagonal covariance.
    """
    return model.covariance(measurement, v, psi_dot)


def _maybe_float(x):
    return None if x is None else float(x)


def _ems_from_dict(d: dict) -> ErrorModelSingleParam:
    return ErrorModelSingleParam(
        baseline=float(d.get("baseline", 0.0)),
        gain_1=float(d.get("gain_1", 0.0)),
        gain_2=_maybe_float(d.get("gain_2", None)),
        corner=_maybe_float(d.get("corner", None)),
    )


def _error_model_from_dict(d: dict) -> ErrorModel:
    """Build ErrorModel (for one DOF) from dict with sub-dicts distance/bearing/psi/v/psi_dot."""
    return ErrorModel(
        distance=_ems_from_dict(d.get("distance", {})),
        bearing=_ems_from_dict(d.get("bearing", {})),
        psi=_ems_from_dict(d.get("psi", {})),
        v=_ems_from_dict(d.get("v", {})),
        psi_dot=_ems_from_dict(d.get("psi_dot", {})),
    )


def measurement_model_from_file(file) -> FRODO_MeasurementModel:
    """
    Load a MeasurementModel from a YAML file path or file-like object.
    Supports either 'fov_rad' or 'fov_deg' in the YAML.
    """

    if not fileExists(file):
        raise FileNotFoundError(f"File not found: {file}")

    data = yaml.safe_load(file) if hasattr(file, "read") else yaml.safe_load(open(file, "r"))

    # Handle FOV in either radians or degrees
    fov = float(data.get("fov", data.get("fov_rad", np.deg2rad(data.get("fov_deg", 0.0)))))

    # Parse components
    components = data.get("components", {})

    # Create covariance model
    covariance = CovarianceModel(
        x=_error_model_from_dict(components.get("x", {})),
        y=_error_model_from_dict(components.get("y", {})),
        psi=_error_model_from_dict(components.get("psi", {}))
    )

    # Create and return the full model
    model = FRODO_MeasurementModel(
        fov=fov,
        min_measurement_distance=float(data.get("min_measurement_distance", 0.0)),
        max_measurement_distance=float(data.get("max_measurement_distance", 2.0)),
        bias_x=float(data.get("bias_x", 0.0)),
        bias_y=float(data.get("bias_y", 0.0)),
        bias_psi=float(data.get("bias_psi", 0.0)),
        covariance=covariance
    )

    return model


def _to_builtin(obj):
    """
    Recursively convert numpy scalar types and arrays to Python builtins
    (float, int, list, dict).
    """
    import numpy as np

    if isinstance(obj, dict):
        return {k: _to_builtin(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_to_builtin(v) for v in obj]
    elif isinstance(obj, tuple):
        return tuple(_to_builtin(v) for v in obj)
    elif isinstance(obj, np.generic):  # np.float64, np.int64, etc.
        return obj.item()
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    else:
        return obj


def measurement_model_to_file(model: FRODO_MeasurementModel, file) -> None:
    if yaml is None:
        raise ImportError(
            "PyYAML is required. Install via `pip install pyyaml` to save to YAML."
        )

    out = {
        "fov": float(model.fov),
        "min_measurement_distance": float(model.min_measurement_distance),
        "max_measurement_distance": float(model.max_measurement_distance),
        "components": {
            "x": {
                "distance": asdict(model.covariance.x.distance),
                "bearing": asdict(model.covariance.x.bearing),
                "psi": asdict(model.covariance.x.psi),
                "v": asdict(model.covariance.x.v),
                "psi_dot": asdict(model.covariance.x.psi_dot),
            },
            "y": {
                "distance": asdict(model.covariance.y.distance),
                "bearing": asdict(model.covariance.y.bearing),
                "psi": asdict(model.covariance.y.psi),
                "v": asdict(model.covariance.y.v),
                "psi_dot": asdict(model.covariance.y.psi_dot),
            },
            "psi": {
                "distance": asdict(model.covariance.psi.distance),
                "bearing": asdict(model.covariance.psi.bearing),
                "psi": asdict(model.covariance.psi.psi),
                "v": asdict(model.covariance.psi.v),
                "psi_dot": asdict(model.covariance.psi.psi_dot),
            },
        },
    }

    # ✅ Convert all numpy types to built-ins before dumping
    out = _to_builtin(out)

    if hasattr(file, "write"):
        yaml.safe_dump(out, file, sort_keys=False)
    else:
        with open(file, "w") as f:
            yaml.safe_dump(out, f, sort_keys=False)


def analyze_measurement_model(
        model: FRODO_MeasurementModel,
        target: Literal['x', 'y', 'psi'] = 'x',
        *,
        std_unit: Literal['m', 'cm'] = 'cm',
        align_component_axes: bool = True,
) -> None:
    """
    Visualize a MeasurementModel for one output DOF (x, y, or psi).

    Changes vs. previous version:
    - Bearing plot shows vertical lines at ±FOV/2.
    - Psi plot's x-axis is in degrees (std for psi remains in radians).
    - Denser grid (major + minor) on all subplots for easier reading.
    - 'std_unit' switch for linear DOFs: plot σ in meters or centimeters.
      (Ignored for target='psi', which is always radians.)
    - 'align_component_axes' switch to align y-axis limits across all 2D component plots.
    - All y-axes are clamped to a minimum of 0.

    Args:
        model: FRODO_MeasurementModel
        target: 'x' | 'y' | 'psi'  -> which DOF to visualize.
        std_unit: 'm' or 'cm' -> scales σ for linear DOFs (x/y). For psi, σ is in radians.
        align_component_axes: if True, all 2D component plots share the same ymax.
    """
    # ============================================================
    # SETTINGS SECTION
    # ============================================================
    settings = {
        "distance_min": float(model.min_measurement_distance),
        "distance_max": float(model.max_measurement_distance),
        "bearing_min": np.deg2rad(-90.0),  # radians (fixed display range)
        "bearing_max": np.deg2rad(90.0),  # radians
        "psi_min": 0.0,  # radians (data grid)
        "psi_max": np.deg2rad(10),  # radians
        "v_min": 0.0,  # m/s
        "v_max": 0.2,  # m/s
        "psi_dot_min": 0.0,  # rad/s (data grid)
        "psi_dot_max": np.deg2rad(180.0),  # rad/s

        "n_points_1d": 300,
        "n_points_3d": 80,

        "figsize": (14, 7.5),
        "font_small": 10,
        "font_tiny": 8,
        "grid_alpha_major": 0.35,
        "grid_alpha_minor": 0.18,
        "ylim_margin": 1.05,  # 5% headroom
    }
    # ============================================================

    # Select the DOF model to visualize
    dof_model: ErrorModel = getattr(model.covariance, target)

    # --- Units and scaling for σ ---
    is_linear = target in ('x', 'y')
    if is_linear:
        if std_unit == 'm':
            sigma_scale = 1.0
            sigma_unit_label = 'm'
        elif std_unit == 'cm':
            sigma_scale = 100.0
            sigma_unit_label = 'cm'
        else:
            raise ValueError("std_unit must be 'm' or 'cm'")
    else:
        sigma_scale = 1.0
        sigma_unit_label = 'rad'  # angular σ always radians

    small = settings["font_small"]
    tiny = settings["font_tiny"]

    # --- Helper to build range including possible corner ---
    def _range_from_knee(ems: ErrorModelSingleParam, default_min: float, default_max: float, n: int):
        corner = ems.corner
        if corner is None or not np.isfinite(corner) or corner <= 0:
            hi = default_max
        else:
            hi = max(default_max, float(corner) * 2.0)
        return np.linspace(default_min, hi, n)

    # Parameter grids (data always in base units: rad, m/s, etc.)
    n1d = settings["n_points_1d"]
    d_grid = np.linspace(settings["distance_min"], settings["distance_max"], n1d)
    b_grid = np.linspace(settings["bearing_min"], settings["bearing_max"], n1d)  # radians
    psi_grid = _range_from_knee(dof_model.psi, settings["psi_min"], settings["psi_max"], n1d)  # radians
    v_grid = _range_from_knee(dof_model.v, settings["v_min"], settings["v_max"], n1d)
    psidot_grid = _range_from_knee(dof_model.psi_dot, settings["psi_dot_min"], settings["psi_dot_max"], n1d)  # rad/s

    # --- Compute stds (then scale for display) ---
    std_d = np.array([dof_model.distance.get_std(d) for d in d_grid]) * sigma_scale
    std_b = np.array([dof_model.bearing.get_std(b) for b in b_grid]) * sigma_scale
    std_psi = np.array([dof_model.psi.get_std(p) for p in psi_grid]) * sigma_scale
    std_v = np.array([dof_model.v.get_std(v) for v in v_grid]) * sigma_scale
    std_psidot = np.array([dof_model.psi_dot.get_std(w) for w in psidot_grid]) * sigma_scale

    # Convert x-axes to degrees where requested (bearing, psi (x-axis only), psi_dot)
    b_grid_deg = np.rad2deg(b_grid)
    psi_grid_deg = np.rad2deg(psi_grid)  # x-axis in degrees for psi plot
    psidot_grid_deg = np.rad2deg(psidot_grid)  # x-axis in deg/s for psi_dot plot

    # --- Matplotlib style ---
    import matplotlib as mpl
    from matplotlib.ticker import AutoMinorLocator
    mpl.rcParams.update({
        'axes.titlesize': small,
        'axes.labelsize': small,
        'xtick.labelsize': tiny,
        'ytick.labelsize': tiny,
        'legend.fontsize': tiny,
    })

    # --- Figure layout ---
    fig = plt.figure(figsize=settings["figsize"])
    gs = fig.add_gridspec(
        nrows=2, ncols=3,
        height_ratios=[1, 1], width_ratios=[1, 1, 1],
        hspace=0.4, wspace=0.35
    )

    ax_d = fig.add_subplot(gs[0, 0])
    ax_b = fig.add_subplot(gs[0, 1])
    ax_psi = fig.add_subplot(gs[0, 2])
    ax_v = fig.add_subplot(gs[1, 0])
    ax_psidot = fig.add_subplot(gs[1, 1])
    ax3d = fig.add_subplot(gs[1, 2], projection='3d')

    # Helper to add dense grid (major + minor) and enforce y>=0
    def _prep_axes(ax):
        ax.grid(True, which='major', alpha=settings["grid_alpha_major"])
        ax.minorticks_on()
        # Use automatic minor locators for both axes
        ax.xaxis.set_minor_locator(AutoMinorLocator())
        ax.yaxis.set_minor_locator(AutoMinorLocator())
        ax.grid(True, which='minor', alpha=settings["grid_alpha_minor"], linestyle=':')
        # y >= 0
        lo, hi = ax.get_ylim()
        ax.set_ylim(bottom=0.0, top=hi)

    # --- 2D plots ---
    # Distance
    ax_d.plot(d_grid, std_d, linewidth=2)
    ax_d.set_title(f"distance → σ_{target} [{sigma_unit_label}]")
    ax_d.set_xlabel("distance [m]")
    ax_d.set_ylabel(f"σ_{target} [{sigma_unit_label}]")
    _prep_axes(ax_d)

    # Bearing (degrees) + FOV vertical lines
    ax_b.plot(b_grid_deg, std_b, linewidth=2)
    ax_b.set_title(f"bearing → σ_{target} [{sigma_unit_label}]")
    ax_b.set_xlabel("bearing [deg]")
    _prep_axes(ax_b)

    # Add FOV lines at ±FOV/2 (converted to degrees)
    if np.isfinite(model.fov) and model.fov > 0:
        fov_half_deg = np.rad2deg(model.fov) / 2.0
        ax_b.axvline(+fov_half_deg, linestyle='--', linewidth=1.5, alpha=0.7)
        ax_b.axvline(-fov_half_deg, linestyle='--', linewidth=1.5, alpha=0.7)

    # Psi plot: x-axis in degrees, σ unit as above
    ax_psi.plot(psi_grid_deg, std_psi, linewidth=2)
    ax_psi.set_title(f"psi → σ_{target} [{sigma_unit_label}]")
    ax_psi.set_xlabel("psi [deg]")  # requested degrees on x-axis
    _prep_axes(ax_psi)

    # v
    ax_v.plot(v_grid, std_v, linewidth=2)
    ax_v.set_title(f"v → σ_{target} [{sigma_unit_label}]")
    ax_v.set_xlabel("v [m/s]")
    ax_v.set_ylabel(f"σ_{target} [{sigma_unit_label}]")
    _prep_axes(ax_v)

    # psi_dot (x-axis in deg/s)
    ax_psidot.plot(psidot_grid_deg, std_psidot, linewidth=2)
    ax_psidot.set_title(f"psi_dot → σ_{target} [{sigma_unit_label}]")
    ax_psidot.set_xlabel("psi_dot [deg/s]")
    _prep_axes(ax_psidot)

    # Optionally align all component plot y-axes to the same max
    if align_component_axes:
        ymax = max(
            float(np.max(std_d)),
            float(np.max(std_b)),
            float(np.max(std_psi)),
            float(np.max(std_v)),
            float(np.max(std_psidot)),
        )
        ymax = max(ymax, 0.0) * settings["ylim_margin"]
        for ax in (ax_d, ax_b, ax_psi, ax_v, ax_psidot):
            ax.set_ylim(0.0, ymax)

    # --- 3D surface (bearing shown in degrees) ---
    n3d = settings["n_points_3d"]
    D, B = np.meshgrid(
        np.linspace(settings["distance_min"], settings["distance_max"], n3d),
        np.linspace(settings["bearing_min"], settings["bearing_max"], n3d),
        indexing='xy'
    )
    Z = np.empty_like(D)
    for i in range(D.shape[0]):
        for j in range(D.shape[1]):
            Z[i, j] = dof_model.get_std(distance=D[i, j], bearing=B[i, j], psi=0.0, v=0.0, psi_dot=0.0)
    Z *= sigma_scale  # apply display scaling to surface as well

    surf = ax3d.plot_surface(D, np.rad2deg(B), Z, linewidth=0, antialiased=True, alpha=0.95)
    ax3d.set_title(f"Total σ_{target}(distance, bearing)", pad=8)
    ax3d.set_xlabel("distance [m]", labelpad=6)
    ax3d.set_ylabel("bearing [deg]", labelpad=6)
    ax3d.set_zlabel(f"σ_{target} [{sigma_unit_label}]", labelpad=6)
    ax3d.set_box_aspect((1.2, 1.0, 0.6))
    ax3d.set_zlim(bottom=0.0)  # min value 0 on z-axis

    mappable = mpl.cm.ScalarMappable(cmap=surf.cmap)
    mappable.set_array(Z)
    cbar = fig.colorbar(mappable, ax=ax3d, fraction=0.046, pad=0.04)
    cbar.ax.tick_params(labelsize=tiny)

    # --- Final layout and title ---
    fig.suptitle(
        f"Measurement Error Model — σ_{target} components and surface",
        fontsize=small, y=0.97
    )
    fig.tight_layout(rect=[0, 0.02, 1, 0.93])
    plt.show()


# === IDENTIFY COVARIANCE MODEL ========================================================================================
@dataclasses.dataclass
class IdentificationDataPoint:
    measurement: np.ndarray  # (x, y, psi)
    v: float  # m/s
    psi_dot: float  # rad/s
    true_relative_state: np.ndarray


def identify_measurement_model(data: list[IdentificationDataPoint], fov: float) -> FRODO_MeasurementModel:
    """
    Identify a covariance model from a list of IdentificationDataPoint objects.
    """


# ==============================
# Minimal demo
# ==============================
if __name__ == '__main__':
    # Example model with easy-to-read knobs
    fov_deg = 90.0
    model = (
        FRODO_MeasurementModel(
            min_measurement_distance=0.0,
            max_measurement_distance=2.0,
            fov=np.deg2rad(fov_deg),
            covariance=CovarianceModel(
                # x-position uncertainties
                x=ErrorModel(
                    distance=ErrorModelSingleParam(baseline=0.02, gain_1=0.02, gain_2=0.12, corner=1.2),
                    bearing=ErrorModelSingleParam(baseline=0.00, gain_1=0.02, gain_2=1, corner=np.deg2rad(30)),
                    psi=ErrorModelSingleParam(baseline=0.00, gain_1=0.02, gain_2=0.5, corner=np.deg2rad(45)),
                    v=ErrorModelSingleParam(baseline=0.00, gain_1=0.3, gain_2=None, corner=None),
                    psi_dot=ErrorModelSingleParam(baseline=0.00, gain_1=0.05, gain_2=0.2, corner=np.deg2rad(45.0)),
                ),

                # y-position uncertainties (often a bit worse near edges)
                y=ErrorModel(
                    distance=ErrorModelSingleParam(baseline=0.02, gain_1=0.02, gain_2=0.12, corner=1.2),
                    bearing=ErrorModelSingleParam(baseline=0.00, gain_1=0.01, gain_2=1, corner=np.deg2rad(45)),
                    psi=ErrorModelSingleParam(baseline=0.00, gain_1=0.00, gain_2=1, corner=1),
                    v=ErrorModelSingleParam(baseline=0.00, gain_1=0.3, gain_2=None, corner=None),
                    psi_dot=ErrorModelSingleParam(baseline=0.00, gain_1=0.1, gain_2=0.4, corner=np.deg2rad(45.0)),
                ),

                # angular uncertainties (radians)
                psi=ErrorModel(
                    distance=ErrorModelSingleParam(baseline=0.01, gain_1=0.02, gain_2=0.12, corner=1.2),
                    bearing=ErrorModelSingleParam(baseline=0.00, gain_1=0.01, gain_2=1, corner=np.deg2rad(45)),
                    psi=ErrorModelSingleParam(baseline=0.00, gain_1=0.00, gain_2=1, corner=1),
                    v=ErrorModelSingleParam(baseline=0.00, gain_1=0.3, gain_2=None, corner=None),
                    psi_dot=ErrorModelSingleParam(baseline=0.00, gain_1=0.1, gain_2=0.4, corner=np.deg2rad(45.0)),
                ),
            ))
    )
    # analyze_measurement_model(model, 'x')

    measurement_model_to_file(model, '../simulation/model.yaml')
    # model = measurement_model_from_file('../simulation/model.yaml')
