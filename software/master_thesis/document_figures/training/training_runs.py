"""
Training run plots for thesis — one figure per policy family.
Layout: 4 rows × 2 cols (8 metrics), shared x-axis.
Stitched run boundaries are marked with dotted vertical lines and circled run numbers.
"""

import os
import pathlib
import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

BASE_PATH = "master_thesis/modules/subgoal_predictor/runs"
OUTPUT_DIR = pathlib.Path(__file__).parent
BIN_SIZE = 20

# Set to a list of policy keys to generate only those, e.g. ["A_bi_gnn"].
# None generates all entries in POLICY_CONFIGS.
POLICIES_TO_RUN = None

# Toggle circled run numbers at boundaries.
# False = dotted lines only; colours still distinguish runs.
SHOW_RUN_NUMBERS = True

# Run colour order: first run = red, second = blue, third = teal/green, then extras.
# Extend if a policy has more runs than colours listed here.
RUN_PALETTE = [
    '#e63946',  # red
    '#457b9d',  # blue
    '#2a9d8f',  # teal-green
    '#f4a261',  # orange
    '#a8dadc',  # light blue
    '#c77dff',  # purple
    '#e9c46a',  # yellow
    '#264653',  # dark slate
]

# Metric tag → display label, in (row, col) order: left col = outcomes, right col = internals
METRICS = [
    ('train/mean_reward',           'Mean Reward'),
    ('train/clip_fraction',         'Clip Fraction'),
    ('train/frac_terminated',       'Frac. Terminated'),
    ('train/mean_entropy_pos',      'Position Entropy'),
    ('train/mean_makespan',         'Mean Makespan [steps]'),
    ('train/mean_skipped_subgoals', 'Skipped Subgoals'),
    ('train/mean_wait_time',        'Mean Wait Time [steps]'),
    ('train/mean_n_crossed',        'Mean Crossings'),
]

# Axes where y should be clipped to [0, 1]
UNIT_METRICS = {'Frac. Terminated', 'Clip Fraction'}

# Each entry in "runs": (subdirectory under BASE_PATH, legend label shown in the plot).
# The label is a free string — rename to whatever is clearest for the thesis
# (e.g. "base", "ft: lr=1e-4", "ft: wait head", …).
# Order the runs list in the order they were trained; the script stitches them left→right.
POLICY_CONFIGS = {
    "A_mlp": {
        "title": "MLP — Scenario A (2×2, 5 agents, 1 gap)",
        "runs": [
            # Each entry: (subdirectory under BASE_PATH, legend label)
            ("homogeneous_gnn/pre_030426/stage1b_20260324_103903", "Stage 1b"),
            ("homogeneous_gnn/pre_030426/stage2_20260327_114822",  "Stage 2: wait head"),
        ],
    },
    "A_hom_gnn": {
        "title": "Homogeneous GNN — Scenario A (2×2, 5 agents, 1 gap)",
        "runs": [
            ("homogeneous_gnn/gnn_ppo_D2_20260403_221437",                "base"),
            ("homogeneous_gnn/gnn_ppo_D2_cont_20260406_144831",           "cont. wait"),
            ("homogeneous_gnn/gnn_ppo_D2_cont_v2_20260407_160009",        "skip pen.=4"),
            ("homogeneous_gnn/gnn_ppo_D2_cont_v3_20260411_174544",        "plan pen.=0.5"),
            ("homogeneous_gnn/gnn_ppo_D2_cont_v3_phase2_20260412_224158", "rand. spawn"),
        ],
    },
    "A_bi_gnn": {
        "title": "Bipartite GNN — Scenario A (2×2, 5 agents, 1 gap)",
        "runs": [
            ("bp_A_20260414_005433",     "base"),
            ("bp_A_ft_20260415_012529",  "ft1"),
            ("bp_A_ft2_20260416_094315", "ft2"),
            ("bp_A_ft3_20260416_235148", "ft3"),
            ("bp_A_ft4_20260419_021501", "ft4"),
            ("bp_A_ft5_20260420_121017", "ft5"),
        ],
    },
    "C_bi_gnn": {
        "title": "Bipartite GNN — Scenario C (3×3, 10 agents, 2 gaps)",
        "runs": [
            ("bp_C_20260415_012323",  "v1"),
            ("bp_C_20260415_110124",  "v2"),
            ("bp_C_20260415_120804",  "v3"),
            ("bp_C_20260415_140332",  "v4"),
            ("bp_C_20260417_181304",  "v5"),
            ("bp_C_20260419_152645",  "v6"),
            ("bp_C_20260420_203814",  "v7"),
            ("bp_C_20260420_235105",  "v8"),
        ],
    },
    "D_bi_gnn": {
        "title": "Bipartite GNN — Scenario D (3×3, 8 agents, 1 gap)",
        "runs": [
            ("bp_D_20260415_012145",  "v1"),
            ("bp_D_20260415_110413",  "v2"),
            ("bp_D2_20260419_234212", "D2-v1"),
            ("bp_D2_20260421_144251", "D2-v2"),
        ],
    },
}


def load_run_data(run_dir: str, run_name: str) -> pd.DataFrame:
    ea = EventAccumulator(run_dir)
    ea.Reload()
    available = set(ea.Tags().get('scalars', []))

    run_df = None
    for tag, label in METRICS:
        if tag not in available:
            continue
        df = pd.DataFrame(ea.Scalars(tag))
        df = df.rename(columns={'value': label, 'step': 'Step'})[['Step', label]]
        run_df = df if run_df is None else pd.merge(run_df, df, on='Step', how='outer')

    if run_df is None:
        return pd.DataFrame()

    run_df['Run'] = run_name
    return run_df.sort_values('Step').reset_index(drop=True)


def stitch_runs(runs_config: list, bin_size: int = BIN_SIZE):
    """Concatenate runs into a single continuous step axis with bin-aligned offsets.

    Returns (df, boundaries, run_midpoints):
      boundaries    — x positions of the dividers between runs (len = n_runs - 1)
      run_midpoints — x centre of each run segment (len = n_runs), used for number labels
    """
    all_data = []
    boundaries = []
    run_midpoints = []
    current_offset = 0

    for path, name in runs_config:
        print(f"  Loading '{name}' from {path} …")
        df = load_run_data(path, name)
        if df.empty:
            print(f"    [warn] no data found, skipping")
            continue

        run_start = current_offset
        df['Step'] = df['Step'] - df['Step'].min() + current_offset
        all_data.append(df)

        max_step = df['Step'].max()
        run_midpoints.append((run_start + max_step) / 2)

        last_bin_x = (max_step // bin_size) * bin_size
        boundary_pos = last_bin_x + bin_size / 2
        boundaries.append(boundary_pos)
        current_offset = last_bin_x + bin_size

    if not all_data:
        return pd.DataFrame(), [], []

    return pd.concat(all_data, ignore_index=True), boundaries[:-1], run_midpoints


def _add_vlines(ax, boundaries: list):
    """Draw vertical dotted lines at run boundaries (called during main plot loop)."""
    for b in boundaries:
        ax.axvline(x=b, color='black', linestyle=':', alpha=0.65, linewidth=1.4)


def _add_run_numbers(axes_row: list, run_midpoints: list):
    """Add circled run numbers above the top-row axes (called AFTER tight_layout).

    Placing annotations after tight_layout means tight_layout never accounts for
    the out-of-axes content and won't add unwanted space below the suptitle.
    """
    if not SHOW_RUN_NUMBERS:
        return
    for ax in axes_row:
        for k, mid in enumerate(run_midpoints):
            ax.text(
                mid, 1.02, str(k + 1),
                transform=ax.get_xaxis_transform(),
                ha='center', va='bottom',
                fontsize=7, fontweight='bold',
                bbox=dict(boxstyle='circle,pad=0.18', fc='white', ec='#333333', lw=0.9),
                clip_on=False,
            )


def plot_policy(df: pd.DataFrame, boundaries: list, run_midpoints: list, title: str, output_path: pathlib.Path):
    bin_size = BIN_SIZE
    df = df.copy()
    df['Binned Step'] = (df['Step'] // bin_size) * bin_size

    sns.set_theme(style="darkgrid")
    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Palatino", "serif"],
        "axes.titlesize": 11,
        "axes.labelsize": 10,
    })

    n_rows, n_cols = 4, 2
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(13, 15), sharex=True,
                             gridspec_kw={'hspace': 0.35, 'wspace': 0.3})
    fig.suptitle(title, fontsize=13, fontweight='bold', y=1.005)

    n_runs = df['Run'].nunique()
    palette = RUN_PALETTE[:n_runs]

    for idx, (tag, label) in enumerate(METRICS):
        row, col = divmod(idx, n_cols)
        ax = axes[row, col]

        if label not in df.columns or df[label].isna().all():
            ax.text(0.5, 0.5, 'no data', transform=ax.transAxes,
                    ha='center', va='center', color='gray', fontsize=9)
            ax.set_title(label, fontweight='bold', pad=20)
            _add_vlines(ax, boundaries)
            continue

        sns.lineplot(
            data=df, x='Binned Step', y=label, hue='Run', ax=ax,
            linewidth=2.0, errorbar='sd', legend=False, palette=palette,
        )

        ax.set_title(label, fontweight='bold', pad=20)
        ax.set_ylabel('')

        if label in UNIT_METRICS:
            ax.set_ylim(0, 1.05)

        _add_vlines(ax, boundaries)

        if row == n_rows - 1:
            ax.set_xlabel('Cumulative PPO Updates', fontsize=10)

    # tight_layout runs before annotations so it doesn't reserve space for them
    plt.tight_layout()
    _add_run_numbers(axes[0, :], run_midpoints)
    fig.savefig(output_path, bbox_inches='tight', dpi=200)
    print(f"  → saved {output_path.name}")
    plt.close(fig)


if __name__ == "__main__":
    configs = {k: v for k, v in POLICY_CONFIGS.items()
               if POLICIES_TO_RUN is None or k in POLICIES_TO_RUN}
    for policy_key, cfg in configs.items():
        print(f"\n{'='*60}")
        print(f"Policy: {policy_key}")

        full_paths = [(os.path.join(BASE_PATH, p), n) for p, n in cfg["runs"]]
        df, boundaries, run_midpoints = stitch_runs(full_paths)

        if df.empty:
            print("  [skip] no data loaded")
            continue

        out = OUTPUT_DIR / f"training_{policy_key}.pdf"
        plot_policy(df, boundaries, run_midpoints, cfg["title"], out)

    print("\nDone.")
