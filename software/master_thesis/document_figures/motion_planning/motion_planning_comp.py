"""Motion planning benchmark and figure generator.

Collects timing and path-length data for two planners:
  1. RRT + CVXPY + flat outputs  (geometric RRT, then Bézier optimisation)
  2. PRM* + CVXPY + flat outputs (pre-built roadmap query, then Bézier)

Run from repo root with venv active:
    python -m master_thesis.document_figures.motion_planning.motion_planning_comp
    python -m master_thesis.document_figures.motion_planning.motion_planning_comp --force   # re-collect
    python -m master_thesis.document_figures.motion_planning.motion_planning_comp --plot-only
"""

import argparse
import dataclasses
import pathlib
import sys
import time

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np
import pandas as pd
import seaborn as sns

try:
    from ompl import base as ob
    from ompl import geometric as og
    # from ompl import control as oc   # kinodynamic RRT — not used
    from ompl import util as ou
except ModuleNotFoundError:
    print(
        "OMPL not found. Install from https://github.com/ompl/ompl/releases",
        file=sys.stderr,
    )
    sys.exit(1)

from master_thesis.modules.motion_planning.mp_functions.ompl_planner import (
    OMPLSmoothPathPlanner, OMPLPlannerConfig, RoadmapBuilder,
)
from master_thesis.modules.motion_planning.mp_functions.opt_safe import FRODOFlatOpt
from master_thesis.modules.motion_planning.mp_functions.mp_tests import _TimedPlanner
from master_thesis.modules.motion_planning.mp_functions.collisions_fcl import AgentCollisionChecker
from master_thesis.scenarios.testbed_importer import load_scenario_yaml


# ── Constants ─────────────────────────────────────────────────────────────────

_SCENARIO_PATH = pathlib.Path(__file__).parent.parent.parent / "scenarios" / "maze_4x4_mp_bench.yaml"
_OUTPUT_DIR    = pathlib.Path(__file__).parent
_NPZ_PATH      = _OUTPUT_DIR / "motion_planning_data.npz"
_PDF_PATH      = _OUTPUT_DIR / "motion_planning_comparison.pdf"

_FRODO_DIMS = (0.157, 0.115, 0.11)   # L, W, H

_RRT_CFG = OMPLPlannerConfig(
    Ts=0.1, v_max=0.3, psi_dot_max=np.pi / 3,
    timelimit=5.0, query_timelimit=0.5, roadmap_time=120.0,
    planner='rrt',
)
_PRM_CFG = OMPLPlannerConfig(
    Ts=0.1, v_max=0.3, psi_dot_max=np.pi / 3,
    timelimit=5.0, query_timelimit=0.5, roadmap_time=120.0,
    planner='rrt',    # used for Bézier-fail fallback
)
# _KINO_CFG = OMPLPlannerConfig(
#     Ts=0.1, v_max=0.3, psi_dot_max=np.pi / 3,
#     timelimit=10.0,   # kinodynamic needs more time in narrow corridors
#     goal_eps=0.15,
#     planner='rrt',
# )


# ── Font helper ───────────────────────────────────────────────────────────────

def _register_lm_fonts() -> str:
    search_dirs = [
        pathlib.Path.home() / "Library" / "Fonts",
        pathlib.Path("/usr/local/texlive/2025/texmf-dist/fonts/opentype/public/lm"),
        pathlib.Path("/usr/local/texlive/2024/texmf-dist/fonts/opentype/public/lm"),
        pathlib.Path("/usr/local/texlive/2023/texmf-dist/fonts/opentype/public/lm"),
    ]
    registered: set[str] = set()
    for d in search_dirs:
        if not d.exists():
            continue
        for p in d.glob("lmroman*.otf"):
            try:
                fm.fontManager.addfont(str(p))
                registered.add(fm.FontProperties(fname=str(p)).get_name())
            except Exception:
                pass
    for name in ("Latin Modern Roman", "LMRoman10", "LM Roman 10"):
        if name in registered:
            return name
    return "serif"


# ── Scenario loading ──────────────────────────────────────────────────────────

def _load_scenario():
    """Load limits, obstacles, start and goal from the YAML scenario."""
    cfg = load_scenario_yaml(_SCENARIO_PATH.read_text())
    obstacles = [
        {"x": o.x, "y": o.y, "psi": o.psi,
         "length": o.length, "width": o.width, "height": o.height}
        for o in cfg.obstacles
    ]
    limits = cfg.limits
    start  = np.array(cfg.agents[0].start_config, dtype=float)
    goal   = np.array([cfg.tasks[0].x, cfg.tasks[0].y, 0.0], dtype=float)
    return limits, obstacles, start, goal


# ── Tri-staged timed planner ──────────────────────────────────────────────────

class _TriStagedTimedPlanner(_TimedPlanner):
    """Extends _TimedPlanner to separately time CVXPY (stage 2) and flat-output (stage 3).

    t_ompl  – inherited from _TimedPlanner: OMPL geometric solve
    t_cvxpy – time in create_bezier() (CVXPY solve)
    t_flat  – time in bezier_to_configurations() (flat-output + temporal scaling)
    t_bezier from parent remains 0 (pipeline overridden without calling super).
    """

    t_cvxpy: float = 0.0
    t_flat:  float = 0.0

    def _run_bezier_pipeline(self, waypoints, start, goal) -> bool:
        sf = self.config.bezier_safety_factor
        self._opt = FRODOFlatOpt(
            self._build_opt_data(waypoints, start, goal),
            dt=self.config.Ts,
            v_max=self.config.v_max * sf,
            psi_dot_max=self.config.psi_dot_max * sf,
        )
        self._opt.find_hyperplanes()
        self._opt.create_optimization_vars()

        t0 = time.perf_counter()
        self._opt.create_bezier()
        self.t_cvxpy += time.perf_counter() - t0

        if not self._opt.feasible:
            return False

        t0 = time.perf_counter()
        self._opt.bezier_to_configurations()
        self.t_flat += time.perf_counter() - t0

        return True

    def solve_with_retries(self, start, goal, roadmap=None) -> tuple[bool, float]:
        self.t_cvxpy = 0.0
        self.t_flat  = 0.0
        return super().solve_with_retries(start, goal, roadmap=roadmap)


# ── Kinodynamic RRT planner (commented out — not used) ────────────────────────

# class _KinodynamicRRTPlanner:
#     def __init__(self, limits, obstacles, agent_dims, config=None): ...
#     def solve(self, start, goal): ...


# ── Data collection ───────────────────────────────────────────────────────────

def collect_mp_data(n_trials: int = 100, output_path: pathlib.Path = _NPZ_PATH) -> pathlib.Path:
    """Run benchmark and save results to *output_path* (.npz).

    Timing breakdown per successful trial:
        t_ompl  – OMPL geometric solve
        t_cvxpy – CVXPY Bézier optimisation
        t_flat  – flat-output + temporal scaling
    PRM* roadmap construction time is excluded (one-time offline cost).
    """
    limits, obstacles, start, goal = _load_scenario()
    results: dict[str, np.ndarray] = {}

    # ── RRT + CVXPY ───────────────────────────────────────────────────────────
    print(f"[1/2] Benchmarking RRT + CVXPY ({n_trials} trials) …")
    rrt = _TriStagedTimedPlanner(limits, obstacles, _FRODO_DIMS, _RRT_CFG)
    t_ompl_l, t_cvxpy_l, t_flat_l, len_l, ok_l = [], [], [], [], []
    for i in range(n_trials):
        success, length = rrt.solve_with_retries(start, goal)
        t_ompl_l.append(rrt.t_ompl);  t_cvxpy_l.append(rrt.t_cvxpy)
        t_flat_l.append(rrt.t_flat);  len_l.append(length); ok_l.append(success)
        if (i + 1) % 10 == 0:
            sr = sum(ok_l) / len(ok_l) * 100
            print(f"  {i+1:3d}/{n_trials}  success rate so far: {sr:.0f}%")
    results |= dict(
        rrt_t_ompl=np.array(t_ompl_l), rrt_t_cvxpy=np.array(t_cvxpy_l),
        rrt_t_flat=np.array(t_flat_l), rrt_length=np.array(len_l),
        rrt_success=np.array(ok_l),
    )

    # ── PRM* + CVXPY ──────────────────────────────────────────────────────────
    print(f"[2/2] Building PRM* roadmap ({_PRM_CFG.roadmap_time:.0f} s) …")
    prm = _TriStagedTimedPlanner(limits, obstacles, _FRODO_DIMS, _PRM_CFG)
    roadmap = prm.build_roadmap()

    print(f"      Benchmarking PRM* + CVXPY ({n_trials} trials) …")
    t_ompl_l, t_cvxpy_l, t_flat_l, len_l, ok_l = [], [], [], [], []
    for i in range(n_trials):
        success, length = prm.solve_with_retries(start, goal, roadmap=roadmap)
        t_ompl_l.append(prm.t_ompl);  t_cvxpy_l.append(prm.t_cvxpy)
        t_flat_l.append(prm.t_flat);  len_l.append(length); ok_l.append(success)
        if (i + 1) % 10 == 0:
            sr = sum(ok_l) / len(ok_l) * 100
            print(f"  {i+1:3d}/{n_trials}  success rate so far: {sr:.0f}%")
    results |= dict(
        prm_t_ompl=np.array(t_ompl_l), prm_t_cvxpy=np.array(t_cvxpy_l),
        prm_t_flat=np.array(t_flat_l), prm_length=np.array(len_l),
        prm_success=np.array(ok_l),
    )

    # ── Kinodynamic RRT (commented out) ──────────────────────────────────────
    # print(f"[3/3] Benchmarking Kinodynamic RRT ({n_trials} trials) …")
    # kino = _KinodynamicRRTPlanner(limits, obstacles, _FRODO_DIMS, _KINO_CFG)
    # ...

    np.savez(output_path, **results)
    print(f"\nSaved → {output_path.absolute()}")
    return output_path


# ── Plotting ──────────────────────────────────────────────────────────────────

def plot_motion_planning_comparison(npz_path: pathlib.Path = _NPZ_PATH):
    """Load benchmark data from *npz_path* and render the comparison figure."""
    plot_rrt_vs_prm(npz_path=npz_path)


def _render_figure(df_time, df_length, success_rates=None, output_path: pathlib.Path = _PDF_PATH):
    font_family = _register_lm_fonts()
    plt.rcParams.update({
        "font.family":    "serif",
        "font.serif":     [font_family, "Palatino", "Times New Roman"],
        "text.usetex":    False,
        "axes.titlesize": 13,
        "axes.labelsize": 10,
    })
    sns.set_theme(style="whitegrid", font=font_family)

    n_methods = len(df_time)
    COLORS = ["#e63946", "#457b9d", "#00b695"][:n_methods]
    GREY   = "#646464"
    ALPHA_STEP1 = 1.0
    ALPHA_STEP2 = 0.7
    ALPHA_STEP3 = 0.5

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))
    # fig.suptitle("Motion Planning — RRT vs. PRM* + CVXPY", fontsize=15, fontweight="bold", y=0.98)

    # ── Left: stacked bar chart (cumulative timing) ───────────────────────────
    methods     = df_time["Method"].tolist()
    y_positions = np.arange(len(methods)) * 0.6
    bar_height  = 0.45 * 0.5   # 30% thinner

    for i, method in enumerate(methods):
        row  = df_time.iloc[i]
        s1   = row["Step1"]
        s12  = row["Step1_2"]
        s123 = row["Step1_2_3"]
        color = COLORS[i]

        ax1.barh(y_positions[i], s1,         left=0,   height=bar_height,
                 color=color, alpha=ALPHA_STEP1, edgecolor="none")
        ax1.barh(y_positions[i], s12 - s1,   left=s1,  height=bar_height,
                 color=color, alpha=ALPHA_STEP2, edgecolor="none")
        ax1.barh(y_positions[i], s123 - s12, left=s12, height=bar_height,
                 color=color, alpha=ALPHA_STEP3, edgecolor="none")

        # Success rate annotation at bar end
        if success_rates is not None:
            sr = success_rates.get(method, 1.0)
            ax1.text(s123 + 0.005, y_positions[i],
                     f"{sr * 100:.0f}% success",
                     va="center", ha="left", fontsize=9, color=GREY)

    ax1.set_yticks(y_positions)
    ax1.set_yticklabels(methods)
    ax1.invert_yaxis()
    # Push bars toward the top; leave explicit space at visual bottom for the legend.
    ax1.set_ylim(bottom=1.4, top=-0.3)

    # Legend: each stage patch is split left/right in the actual method colors.
    from matplotlib.legend_handler import HandlerBase
    from matplotlib.patches import Polygon as _Poly

    class _SplitPatch(HandlerBase):
        """Legend key split diagonally (top-left / bottom-right) in method colors."""

        def __init__(self, colors, alpha):
            self._colors = colors
            self._alpha  = alpha
            super().__init__()

        def create_artists(self, legend, orig_handle,
                           xdescent, ydescent, width, height, fontsize, trans):
            x, y, w, h = xdescent, ydescent, width, height
            # Diagonal from bottom-left (x, y) to top-right (x+w, y+h):
            #   lower-right triangle → colors[0]  (first method)
            #   upper-left  triangle → colors[1]  (second method)
            return [
                _Poly([(x, y), (x + w, y), (x + w, y + h)],
                      facecolor=self._colors[0], alpha=self._alpha,
                      transform=trans, edgecolor="none"),
                _Poly([(x, y), (x, y + h), (x + w, y + h)],
                      facecolor=self._colors[1], alpha=self._alpha,
                      transform=trans, edgecolor="none"),
            ]

    l1 = mpatches.Patch(label="1. OMPL geometric solve")
    l2 = mpatches.Patch(label="2. CVXPY Bézier optimisation")
    l3 = mpatches.Patch(label="3. Flat-output & temporal scaling")
    handler_map = {
        l1: _SplitPatch(COLORS, ALPHA_STEP1),
        l2: _SplitPatch(COLORS, ALPHA_STEP2),
        l3: _SplitPatch(COLORS, ALPHA_STEP3),
    }
    ax1.legend(handles=[l1, l2, l3], handler_map=handler_map,
               ncol=1, loc="lower right", frameon=True)
    ax1.set_xlabel("Mean computation time [s]")
    ax1.set_ylabel("")
    ax1.set_title("Motion Planning Pipeline Timing", pad=14)
    sns.despine(left=True, bottom=True, ax=ax1)

    # ── Right: path length distribution ──────────────────────────────────────
    sns.violinplot(
        data=df_length, x="Method", y="Path Length",
        bw_adjust=0.5, cut=1, linewidth=1,
        palette=COLORS, ax=ax2, hue="Method", legend=False,
    )
    ax2.set_xlabel("")
    ax2.set_ylabel("Path length [m]")
    ax2.set_title("Path Length Distribution", pad=14)
    lo, hi = ax2.get_ylim()
    ax2.set_ylim(lo, hi + (hi - lo) * 0.15)
    sns.despine(left=True, bottom=True, ax=ax2)

    plt.tight_layout()
    # fig.subplots_adjust(top=0.84)
    fig.savefig(output_path, bbox_inches="tight")
    print(f"Figure saved → {output_path.absolute()}")
    plt.show()


# ── RRT vs PRM* only ─────────────────────────────────────────────────────────

_PDF_PATH_RRT_PRM = _OUTPUT_DIR / "motion_planning_rrt_vs_prm.pdf"


def plot_rrt_vs_prm(npz_path: pathlib.Path = _NPZ_PATH):
    """Plot timing and path-length comparison for RRT and PRM* only."""
    data = np.load(npz_path)

    rrt_ok = data["rrt_success"].astype(bool)
    prm_ok = data["prm_success"].astype(bool)

    def _mean(arr, mask):
        vals = arr[mask]
        return float(vals.mean()) if vals.size > 0 else 0.0

    methods = ["RRT + CVXPY", "PRM* + CVXPY"]

    time_data = {
        "Method": methods,
        "Step1": [
            _mean(data["rrt_t_ompl"], rrt_ok),
            _mean(data["prm_t_ompl"], prm_ok),
        ],
        "Step1_2": [
            _mean(data["rrt_t_ompl"] + data["rrt_t_cvxpy"], rrt_ok),
            _mean(data["prm_t_ompl"] + data["prm_t_cvxpy"], prm_ok),
        ],
        "Step1_2_3": [
            _mean(data["rrt_t_ompl"] + data["rrt_t_cvxpy"] + data["rrt_t_flat"], rrt_ok),
            _mean(data["prm_t_ompl"] + data["prm_t_cvxpy"] + data["prm_t_flat"], prm_ok),
        ],
    }
    df_time = pd.DataFrame(time_data)

    lengths = []
    for method, arr, mask in [
        ("RRT + CVXPY",  data["rrt_length"], rrt_ok),
        ("PRM* + CVXPY", data["prm_length"], prm_ok),
    ]:
        for v in arr[mask]:
            lengths.append({"Method": method, "Path Length": float(v)})
    df_length = pd.DataFrame(lengths)

    success_rates = {
        "RRT + CVXPY":  rrt_ok.mean(),
        "PRM* + CVXPY": prm_ok.mean(),
    }

    _render_figure(df_time, df_length, success_rates, output_path=_PDF_PATH_RRT_PRM)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MP benchmark & figure")
    parser.add_argument("--trials",    type=int, default=100)
    parser.add_argument("--force",     action="store_true", help="re-run benchmark even if .npz exists")
    parser.add_argument("--plot-only", action="store_true", help="skip collection, plot existing .npz")
    args = parser.parse_args()

    if not args.plot_only and (args.force or not _NPZ_PATH.exists()):
        collect_mp_data(n_trials=args.trials, output_path=_NPZ_PATH)

    if not _NPZ_PATH.exists():
        print(f"No data file found at {_NPZ_PATH}. Run without --plot-only first.", file=sys.stderr)
        sys.exit(1)

    plot_rrt_vs_prm(npz_path=_NPZ_PATH)
