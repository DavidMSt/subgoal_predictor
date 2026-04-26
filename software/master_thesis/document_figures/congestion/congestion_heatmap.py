"""Congestion heatmap figure.

Renders one KDE panel per entry in PANELS, loaded from positions_*.npz files
produced by run_eval.py.  Any combination of methods/runs can be compared —
just point PANELS at the relevant files.

Edit PANELS and SCENARIO at the top, then run from the repo root:

    python -m master_thesis.document_figures.congestion.congestion_heatmap

Each positions_*.npz contains:
    xy        — (N, 2) float32  all agent positions from all episodes × steps
    ep_steps  — (n_episodes,) int  steps per episode (available for filtering)
"""

import pathlib
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.font_manager as fm

# ── Configuration ─────────────────────────────────────────────────────────────

_INF = pathlib.Path('master_thesis/document_figures/inference')
_OUT = pathlib.Path(__file__).parent / 'congestion_heatmap.pdf'

# Scenario YAML name — used to draw obstacles at correct coordinates.
SCENARIO = 'rl_8n_fixed_1gap_3x3'

# Each panel: (display_label, path_to_positions_npz)
# Mix and match freely from any run_eval.py output.
PANELS = [
    ('D · No Subgoal',    _INF / 'positions_D_0sg_50ep.npz'),
    ('D · Bipartite GNN', _INF / 'positions_D_bi_gnn_50ep.npz'),
]

# ── Font ──────────────────────────────────────────────────────────────────────

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

# ── Obstacle drawing from scenario YAML ───────────────────────────────────────

def _load_obstacles(scenario_name: str) -> tuple[list[dict], dict]:
    """Return (obstacle_rects, limits) from the scenario YAML."""
    import math
    from master_thesis.scenarios.testbed_importer import load_scenario_yaml
    yaml_path = pathlib.Path('master_thesis/scenarios') / f'{scenario_name}.yaml'
    cfg = load_scenario_yaml(yaml_path.read_text())

    rects = []
    for obs in cfg.obstacles:
        # psi=0 → length along +X; psi=±π/2 → length along +Y (swap dims).
        is_vertical = abs(abs(obs.psi) - math.pi / 2) < 0.1
        x_ext = obs.width  if is_vertical else obs.length
        y_ext = obs.length if is_vertical else obs.width
        rects.append({'x': obs.x - x_ext / 2, 'y': obs.y - y_ext / 2,
                      'w': x_ext, 'h': y_ext})

    lim = cfg.limits   # [[x_lo, x_hi], [y_lo, y_hi]]
    return rects, lim


def _draw_obstacles(ax, rects: list[dict]) -> None:
    for r in rects:
        ax.add_patch(patches.Rectangle(
            (r['x'], r['y']), r['w'], r['h'],
            linewidth=0.8, edgecolor='black', facecolor='#2c3e50', alpha=0.85,
        ))

# ── Plotting ──────────────────────────────────────────────────────────────────

# Cubehelix start values mapped to panel index — cycle if more than 3 panels.
_CMAP_STARTS = [0, 2, 1, 3]


def plot(
    panels: list[tuple[str, pathlib.Path]] = PANELS,
    scenario: str                           = SCENARIO,
    output_path: pathlib.Path               = _OUT,
) -> None:
    font_family = _register_lm_fonts()
    plt.rcParams.update({
        'font.family': 'serif',
        'font.serif':  [font_family, 'Palatino', 'Times New Roman'],
        'text.usetex': False,
    })
    sns.set_theme(style='white', font=font_family)

    obstacle_rects, lim = _load_obstacles(scenario)
    x_lo, x_hi = lim[0]
    y_lo, y_hi = lim[1]

    n = len(panels)
    fig, axes = plt.subplots(1, n, figsize=(8 * n, 8), sharex=True, sharey=True)
    if n == 1:
        axes = [axes]

    for ax, (label, npz_path), cstart in zip(axes, panels, _CMAP_STARTS):
        data = np.load(npz_path)
        xy   = data['xy']                      # (N, 2)
        x, y = xy[:, 0], xy[:, 1]

        cmap = sns.cubehelix_palette(start=cstart, light=1, as_cmap=True)
        sns.kdeplot(
            x=x, y=y,
            cmap=cmap, fill=True,
            thresh=0.03, levels=25,
            alpha=0.85,
            ax=ax,
        )

        _draw_obstacles(ax, obstacle_rects)

        ax.set_xlim(x_lo, x_hi)
        ax.set_ylim(y_lo, y_hi)
        ax.set_aspect('equal')
        ax.set_title(label, fontsize=16, fontweight='bold', pad=14)
        ax.set_xlabel('x [m]', fontsize=12)
        if ax is axes[0]:
            ax.set_ylabel('y [m]', fontsize=12)

        n_samples = len(x)
        ax.text(0.02, 0.02, f'n = {n_samples:,} samples',
                transform=ax.transAxes, fontsize=9, color='#555555',
                va='bottom', ha='left')

    plt.tight_layout()
    fig.savefig(output_path, bbox_inches='tight')
    print(f'Heatmap saved → {output_path.absolute()}')


if __name__ == '__main__':
    plot()
