"""Scenario C and D inference comparison — 2-method, 2×3 layout per scenario.

Each scenario (C, D) produces a separate figure with the same panel structure.

2×3 layout:
  [0,0] Termination rate        — horizontal bar
  [0,1] Makespan                — box + strip (terminated episodes only)
  [0,2] Gap crossings            — box + strip
  [1,0] OMPL wall time          — box + strip
  [1,1] Mean prescribed wait    — mixed: violin (GNN) + "always 0" (0sg)
  [1,2] Subgoals reached        — mixed: box+strip (GNN) + "always 0" (0sg)

Run from repo root:
    python -m master_thesis.document_figures.inference.plot_inference_comparison
"""

import pathlib
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import seaborn as sns

# ── Configuration ─────────────────────────────────────────────────────────────

_DIR = pathlib.Path(__file__).parent

_SCENARIOS: dict[str, dict] = {
    "C": {
        "methods": {
            "C_0sg":    ("No Subgoal",    "#999999"),
            "C_bi_gnn": ("Bipartite GNN", "#e63946"),
        },
        "zero_subgoal_keys": {"C_0sg"},
        "output": _DIR / "eval_C_comparison.pdf",
        "title": "Scenario C",
    },
    "D": {
        "methods": {
            "D_0sg":    ("No Subgoal",    "#999999"),
            "D_bi_gnn": ("Bipartite GNN", "#e63946"),
        },
        "zero_subgoal_keys": {"D_0sg"},
        "output": _DIR / "eval_D_comparison.pdf",
        "title": "Scenario D",
    },
}

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

# ── Data loading ──────────────────────────────────────────────────────────────

def _load(key: str, label: str, color: str) -> dict:
    candidates = sorted(_DIR.glob(f"eval_{key}_*.npz"))
    if not candidates:
        raise FileNotFoundError(f"No npz found for '{key}' in {_DIR}")
    path = candidates[-1]
    d = dict(np.load(path))
    d["_label"] = label
    d["_color"] = color
    n    = len(d["terminated"])
    term = d["terminated"].mean()
    print(f"  {key:15s}  n={n}  term={term:.0%}  "
          f"makespan_mean={d['makespan'].mean():.0f}  "
          f"makespan_std={d['makespan'].std():.0f}")
    return d

# ── Panel helpers ─────────────────────────────────────────────────────────────

def _annotate_means(ax, df, y_col, labels, skip_labels=None):
    """Print mean value above each group's highest data point."""
    skip_labels = skip_labels or set()
    lo, hi = ax.get_ylim()
    span = hi - lo
    ax.set_ylim(lo, hi + 0.15 * span)
    for i, label in enumerate(labels):
        if label in skip_labels:
            continue
        vals = df[df["Method"] == label][y_col].dropna()
        if len(vals) == 0:
            continue
        ax.text(i, float(vals.max()) + 0.04 * span, f"{vals.mean():.1f}",
                ha="center", va="bottom", fontsize=7.5,
                color="#222222", fontweight="bold")


def _box_strip(ax, df, y_col, labels, palette, title, ylabel):
    sns.boxplot(
        data=df, x="Method", y=y_col,
        order=labels, hue="Method", hue_order=labels, palette=palette,
        legend=False, width=0.25, linewidth=1, fliersize=0,
        ax=ax,
    )
    sns.stripplot(
        data=df, x="Method", y=y_col,
        order=labels, hue="Method", hue_order=labels, palette=palette,
        legend=False, size=3, alpha=0.35, jitter=True,
        ax=ax,
    )
    ax.set_xlabel("")
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontweight="bold")
    sns.despine(ax=ax, left=True, bottom=True)
    _annotate_means(ax, df, y_col, labels)


def _mixed_violin(ax, df, y_col, labels, palette, title, ylabel, zero_labels: set[str]):
    """Violin for GNN runs; dashed 'always 0' annotation for 0sg baselines."""
    policy_labels = [l for l in labels if l not in zero_labels]
    policy_df = df[df["Method"].isin(policy_labels)]

    sns.violinplot(
        data=policy_df, x="Method", y=y_col,
        order=labels, hue="Method", hue_order=labels, palette=palette, legend=False,
        bw_adjust=0.6, cut=0, linewidth=1, inner="box", width=0.4,
        ax=ax,
    )
    lo, hi = ax.get_ylim()
    for zero_label in zero_labels:
        if zero_label not in labels:
            continue
        x_pos = labels.index(zero_label)
        color = palette[zero_label]
        ax.plot([x_pos - 0.2, x_pos + 0.2], [0, 0],
                color=color, linewidth=2, linestyle="--", zorder=5)
        ax.text(x_pos, (hi - lo) * 0.04, "always 0",
                color=color, va="bottom", ha="center",
                fontsize=8.5, style="italic", zorder=6)
    ax.set_xlabel("")
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontweight="bold")
    sns.despine(ax=ax, left=True, bottom=True)
    _annotate_means(ax, df, y_col, labels, skip_labels=zero_labels)


def _mixed_box_strip(ax, df, y_col, labels, palette, title, ylabel, zero_labels: set[str]):
    """Box+strip for GNN runs; dashed 'always 0' annotation for 0sg baselines."""
    policy_labels = [l for l in labels if l not in zero_labels]
    policy_df = df[df["Method"].isin(policy_labels)]

    sns.boxplot(
        data=policy_df, x="Method", y=y_col,
        order=labels, hue="Method", hue_order=labels, palette=palette, legend=False,
        width=0.25, linewidth=1, fliersize=0,
        ax=ax,
    )
    sns.stripplot(
        data=policy_df, x="Method", y=y_col,
        order=labels, hue="Method", hue_order=labels, palette=palette, legend=False,
        size=3, alpha=0.4, jitter=True,
        ax=ax,
    )
    lo, hi = ax.get_ylim()
    for zero_label in zero_labels:
        if zero_label not in labels:
            continue
        x_pos = labels.index(zero_label)
        color = palette[zero_label]
        ax.plot([x_pos - 0.2, x_pos + 0.2], [0, 0],
                color=color, linewidth=2, linestyle="--", zorder=5)
        ax.text(x_pos, (hi - lo) * 0.04, "always 0",
                color=color, va="bottom", ha="center",
                fontsize=8.5, style="italic", zorder=6)
    ax.set_xlabel("")
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontweight="bold")
    sns.despine(ax=ax, left=True, bottom=True)
    _annotate_means(ax, df, y_col, labels, skip_labels=zero_labels)

# ── Per-scenario figure ───────────────────────────────────────────────────────

def _render_scenario(scenario_key: str, font_family: str) -> None:
    cfg = _SCENARIOS[scenario_key]
    methods_cfg = cfg["methods"]
    zero_keys   = cfg["zero_subgoal_keys"]
    output_path = cfg["output"]

    print(f"\nLoading {scenario_key} data...")
    methods = [_load(k, label, color) for k, (label, color) in methods_cfg.items()]

    labels  = [m["_label"] for m in methods]
    colors  = [m["_color"] for m in methods]
    palette = dict(zip(labels, colors))
    zero_display = {methods_cfg[k][0] for k in zero_keys}

    # Build long-form DataFrames
    term_rows, mk_rows, nc_rows, wt_rows, mw_rows, nr_rows = [], [], [], [], [], []
    for m in methods:
        term  = m["terminated"].astype(bool)
        label = m["_label"]

        term_rows.append({"Method": label, "Rate": float(term.mean()), "Color": m["_color"]})
        for v in m["makespan"][term]:
            mk_rows.append({"Method": label, "Makespan (steps)": float(v)})
        for v in m["n_crossed"]:
            nc_rows.append({"Method": label, "Gap Crossings": int(v)})
        for v in m["wall_time"]:
            wt_rows.append({"Method": label, "OMPL Wall Time (s)": float(v)})
        for v in m["mean_wait"]:
            mw_rows.append({"Method": label, "Mean Wait (s)": float(v)})
        for v in m["n_reached"]:
            nr_rows.append({"Method": label, "Subgoals Reached": int(v)})

    df_mk = pd.DataFrame(mk_rows)
    df_nc = pd.DataFrame(nc_rows)
    df_wt = pd.DataFrame(wt_rows)
    df_mw = pd.DataFrame(mw_rows)
    df_nr = pd.DataFrame(nr_rows)

    GREY = "#444444"
    fig, axes = plt.subplots(2, 3, figsize=(14, 8))
    fig.subplots_adjust(hspace=0.38, wspace=0.28)

    # ── [0,0] Termination rate ────────────────────────────────────────────────
    ax = axes[0, 0]
    for i, row in enumerate(term_rows):
        r = row["Rate"]
        ax.barh(i, r, color=row["Color"], height=0.5, zorder=3)
        ax.text(r + 0.012, i, f"{r:.0%}", va="center", ha="left",
                fontsize=9.5, color=GREY)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.18)
    ax.set_xlabel("Termination rate")
    ax.set_title("Success Rate", fontweight="bold")
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.grid(axis="x", linestyle="--", alpha=0.35, zorder=0)
    sns.despine(ax=ax, left=True, bottom=False)

    # ── [0,1] Makespan — box + strip ─────────────────────────────────────────
    _box_strip(axes[0, 1], df_mk, "Makespan (steps)", labels, palette,
               "Makespan Distribution\n(terminated episodes only)", "Makespan (steps)")

    # ── [0,2] Gap crossings — box + strip ────────────────────────────────────
    _box_strip(axes[0, 2], df_nc, "Gap Crossings", labels, palette,
               "Gap Crossings", "Crossings / episode")

    # ── [1,0] Wall time — box + strip ────────────────────────────────────────
    _box_strip(axes[1, 0], df_wt, "OMPL Wall Time (s)", labels, palette,
               "OMPL Wall Time", "Wall time (s)")

    # ── [1,1] Mean prescribed wait — mixed violin ────────────────────────────
    _mixed_violin(axes[1, 1], df_mw, "Mean Wait (s)", labels, palette,
                  "Mean Prescribed Wait\n(temporal staggering)", "Mean wait (s)",
                  zero_display)

    # ── [1,2] Subgoals reached — mixed box+strip ─────────────────────────────
    _mixed_box_strip(axes[1, 2], df_nr, "Subgoals Reached", labels, palette,
                     "Subgoals Reached", "Subgoals / episode", zero_display)

    plt.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    print(f"Figure saved → {output_path.absolute()}")
    plt.show()

# ── Entry point ───────────────────────────────────────────────────────────────

def render() -> None:
    font_family = _register_lm_fonts()
    plt.rcParams.update({
        "font.family": "serif",
        "font.serif":  [font_family, "Palatino", "Times New Roman"],
        "text.usetex": False,
    })
    sns.set_theme(style="whitegrid", font=font_family)

    _render_scenario("C", font_family)
    _render_scenario("D", font_family)


if __name__ == "__main__":
    render()
