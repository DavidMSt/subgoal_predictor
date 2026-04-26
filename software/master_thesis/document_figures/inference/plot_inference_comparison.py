"""Inference evaluation comparison figure — 4-run, 6-panel edition.

2×3 layout:
  [0,0] Termination rate      — horizontal bar
  [0,1] Makespan              — box + strip (terminated episodes only)
  [0,2] Failed OMPL plans     — box + strip (discrete count data)
  [1,0] OMPL wall time        — box + strip
  [1,1] Mean prescribed wait  — mixed: violin (GNN runs) + "always 0" (baselines)
  [1,2] Subgoals reached      — mixed: box+strip (GNN runs) + "always 0" (baselines)

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

# key → (display label, npz filename, hex color)
_ALL_METHODS: dict[str, tuple[str, str, str]] = {
    "C_0sg":    ("C · No Subgoal",    "eval_C_0sg_50ep.npz",    "#999999"),
    "C_bi_gnn": ("C · Bipartite GNN", "eval_C_bi_gnn_50ep.npz", "#457b9d"),
    "D_0sg":    ("D · No Subgoal",    "eval_D_0sg_50ep.npz",    "#f4a261"),
    "D_bi_gnn": ("D · Bipartite GNN", "eval_D_bi_gnn_50ep.npz", "#e63946"),
}

ACTIVE_METHODS = ["C_0sg", "C_bi_gnn", "D_0sg", "D_bi_gnn"]

# Keys that have no subgoal mechanism — get "always 0" treatment on panels 5 & 6
ZERO_SUBGOAL_KEYS = {"C_0sg", "D_0sg"}

_PDF_PATH = _DIR / "eval_comparison.pdf"

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

def _load_method(key: str) -> dict:
    label, fname, color = _ALL_METHODS[key]
    path = _DIR / fname
    if not path.exists():
        raise FileNotFoundError(f"Data file for '{key}' not found: {path}")
    d = dict(np.load(path))
    d["_label"] = label
    d["_color"] = color
    d["_key"]   = key
    return d

# ── Panel helpers ─────────────────────────────────────────────────────────────

def _box_strip(ax, df, y_col, labels, palette, title, ylabel):
    sns.boxplot(
        data=df, x="Method", y=y_col,
        order=labels, hue="Method", hue_order=labels, palette=palette, legend=False,
        width=0.45, linewidth=1, fliersize=0,
        ax=ax,
    )
    sns.stripplot(
        data=df, x="Method", y=y_col,
        order=labels, hue="Method", hue_order=labels, palette=palette, legend=False,
        size=3, alpha=0.4, jitter=True,
        ax=ax,
    )
    ax.set_xlabel("")
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontweight="bold")
    sns.despine(ax=ax, left=True, bottom=True)


def _mixed_box_strip(ax, df, y_col, labels, palette, title, ylabel,
                     zero_labels: set[str]):
    """Box+strip for GNN runs; dashed 'always 0' annotation for baselines."""
    policy_labels = [l for l in labels if l not in zero_labels]
    policy_df = df[df["Method"].isin(policy_labels)]

    sns.boxplot(
        data=policy_df, x="Method", y=y_col,
        order=labels, hue="Method", hue_order=labels, palette=palette, legend=False,
        width=0.45, linewidth=1, fliersize=0,
        ax=ax,
    )
    sns.stripplot(
        data=policy_df, x="Method", y=y_col,
        order=labels, hue="Method", hue_order=labels, palette=palette, legend=False,
        size=3, alpha=0.4, jitter=True,
        ax=ax,
    )

    for zero_label in zero_labels:
        if zero_label not in labels:
            continue
        x_pos = labels.index(zero_label)
        color = palette[zero_label]
        ax.plot([x_pos - 0.25, x_pos + 0.25], [0, 0],
                color=color, linewidth=2, linestyle="--", zorder=5)
        ax.text(x_pos, 0, "  always 0",
                color=color, va="center", ha="left",
                fontsize=8.5, style="italic", zorder=6)

    ax.set_xlabel("")
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontweight="bold")
    sns.despine(ax=ax, left=True, bottom=True)


def _mixed_violin(ax, df, y_col, labels, palette, title, ylabel,
                  zero_labels: set[str]):
    """Violin for GNN runs; dashed 'always 0' annotation for baselines."""
    policy_labels = [l for l in labels if l not in zero_labels]
    policy_df = df[df["Method"].isin(policy_labels)]

    sns.violinplot(
        data=policy_df, x="Method", y=y_col,
        order=labels, hue="Method", hue_order=labels, palette=palette, legend=False,
        bw_adjust=0.6, cut=0, linewidth=1, inner="box",
        ax=ax,
    )

    for zero_label in zero_labels:
        if zero_label not in labels:
            continue
        x_pos = labels.index(zero_label)
        color = palette[zero_label]
        ax.plot([x_pos - 0.25, x_pos + 0.25], [0, 0],
                color=color, linewidth=2, linestyle="--", zorder=5)
        ax.text(x_pos, 0, "  always 0",
                color=color, va="center", ha="left",
                fontsize=8.5, style="italic", zorder=6)

    ax.set_xlabel("")
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontweight="bold")
    sns.despine(ax=ax, left=True, bottom=True)

# ── Main figure ───────────────────────────────────────────────────────────────

def render(
    active: list[str] = ACTIVE_METHODS,
    output_path: pathlib.Path = _PDF_PATH,
) -> None:
    font_family = _register_lm_fonts()
    plt.rcParams.update({
        "font.family": "serif",
        "font.serif":  [font_family, "Palatino", "Times New Roman"],
        "text.usetex": False,
    })
    sns.set_theme(style="whitegrid", font=font_family)

    methods = [_load_method(k) for k in active]
    labels  = [m["_label"] for m in methods]
    colors  = [m["_color"] for m in methods]
    palette = dict(zip(labels, colors))

    zero_display = {_ALL_METHODS[k][0] for k in ZERO_SUBGOAL_KEYS if k in active}

    # Build long-form DataFrames
    term_rows, mk_rows, nf_rows, wt_rows, ws_rows, nr_rows = [], [], [], [], [], []

    for m in methods:
        term  = m["terminated"].astype(bool)
        label = m["_label"]

        term_rows.append({"Method": label, "Rate": float(term.mean()), "Color": m["_color"]})
        for v in m["makespan"][term]:
            mk_rows.append({"Method": label, "Makespan (steps)": float(v)})
        for v in m["n_failed"]:
            nf_rows.append({"Method": label, "Failed Plans": int(v)})
        for v in m["wall_time"]:
            wt_rows.append({"Method": label, "OMPL Wall Time (s)": float(v)})
        for v in m["mean_wait"]:
            ws_rows.append({"Method": label, "Mean Wait (s)": float(v)})
        for v in m["n_reached"]:
            nr_rows.append({"Method": label, "Subgoals Reached": int(v)})

    df_mk = pd.DataFrame(mk_rows)
    df_nf = pd.DataFrame(nf_rows)
    df_wt = pd.DataFrame(wt_rows)
    df_ws = pd.DataFrame(ws_rows)
    df_nr = pd.DataFrame(nr_rows)

    GREY = "#444444"
    fig, axes = plt.subplots(2, 3, figsize=(16, 10))
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

    # ── [0,2] Failed plans — box + strip ─────────────────────────────────────
    _box_strip(axes[0, 2], df_nf, "Failed Plans", labels, palette,
               "Failed OMPL Plans", "Failed plans / episode")

    # ── [1,0] Wall time — box + strip ────────────────────────────────────────
    _box_strip(axes[1, 0], df_wt, "OMPL Wall Time (s)", labels, palette,
               "OMPL Wall Time", "Wall time (s)")

    # ── [1,1] Mean prescribed wait — mixed violin ────────────────────────────
    _mixed_violin(axes[1, 1], df_ws, "Mean Wait (s)", labels, palette,
                  "Mean Prescribed Wait\n(temporal staggering)", "Mean wait (s)", zero_display)

    # ── [1,2] Subgoals reached — mixed box+strip ─────────────────────────────
    _mixed_box_strip(axes[1, 2], df_nr, "Subgoals Reached", labels, palette,
                     "Subgoals Reached", "Subgoals / episode", zero_display)

    plt.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    print(f"Figure saved -> {output_path.absolute()}")
    plt.show()


if __name__ == "__main__":
    render()
