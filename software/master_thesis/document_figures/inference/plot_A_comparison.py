"""Scenario A inference comparison — 4-method, 2×2 layout.

All methods achieve near-100% termination on this simple scenario,
so makespan variance is the primary discriminator.

2×2 layout:
  [0,0] Termination rate        — horizontal bar
  [0,1] Makespan distribution   — box + strip (all episodes)
  [1,0] OMPL wall time          — box + strip
  [1,1] Subgoals reached        — mixed: box+strip (GNN/MLP) + "always 0" (0sg)

Run from repo root:
    python -m master_thesis.document_figures.inference.plot_A_comparison
"""

import pathlib
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import seaborn as sns

# ── Configuration ─────────────────────────────────────────────────────────────

_DIR = pathlib.Path(__file__).parent

_METHODS: dict[str, tuple[str, str]] = {
    "A_0sg":     ("No Subgoal",      "#999999"),
    "A_mlp":     ("MLP",             "#00b695"),
    "A_hom_gnn": ("Homogeneous GNN", "#457b9d"),
    "A_bi_gnn":  ("Bipartite GNN",   "#e63946"),
}

ZERO_SUBGOAL_KEYS = {"A_0sg"}

_PDF_PATH = _DIR / "eval_A_comparison.pdf"
_BOX_WIDTH = 0.25

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

def _load() -> tuple[list[str], list[str], dict[str, str], list[dict]]:
    methods = []
    for key in _METHODS:
        candidates = sorted(_DIR.glob(f"eval_{key}_*.npz"))
        if not candidates:
            raise FileNotFoundError(f"No npz found for '{key}' in {_DIR}")
        path = candidates[-1]
        d    = dict(np.load(path))
        label, color = _METHODS[key]
        d["_label"] = label
        d["_color"] = color
        methods.append(d)
        n    = len(d["terminated"])
        term = d["terminated"].mean()
        print(f"  {key:15s}  n={n}  term={term:.0%}  "
              f"makespan_mean={d['makespan'].mean():.0f}  "
              f"makespan_std={d['makespan'].std():.0f}")
    labels  = [m["_label"] for m in methods]
    colors  = [m["_color"] for m in methods]
    palette = dict(zip(labels, colors))
    return labels, colors, palette, methods

# ── Panel helpers ─────────────────────────────────────────────────────────────

def _annotate_means(ax, df, y_col, labels, skip_labels=None, box_half_width=None):
    """Print mean value next to each box, at the height of the mean."""
    if box_half_width is None:
        box_half_width = _BOX_WIDTH / 2
    skip_labels = skip_labels or set()
    for i, label in enumerate(labels):
        if label in skip_labels:
            continue
        vals = df[df["Method"] == label][y_col].dropna()
        if len(vals) == 0:
            continue
        mean_val = float(vals.mean())
        ax.text(
            i + box_half_width + 0.06, mean_val, f"{mean_val:.1f}",
            ha="left", va="center", fontsize=7.5,
            color="#222222", fontweight="bold",
        )


def _annotate_zero(ax, labels, zero_labels, palette):
    """Dashed line at y=0 and 'always 0' italic text with consistent spacing."""
    for zero_label in zero_labels:
        if zero_label not in labels:
            continue
        x_pos = labels.index(zero_label)
        color = palette[zero_label]
        ax.plot([x_pos - 0.15, x_pos + 0.15], [0, 0],
                color=color, linewidth=1.5, linestyle="--", zorder=5)
        ax.annotate(
            "always 0",
            xy=(x_pos, 0), xytext=(0, 3),
            xycoords="data", textcoords="offset points",
            ha="center", va="bottom",
            fontsize=8.5, style="italic", color=color, zorder=6,
        )


def _box_strip(ax, df, y_col, labels, palette, title, ylabel, box_width=_BOX_WIDTH):
    sns.boxplot(
        data=df, x="Method", y=y_col,
        order=labels, hue="Method", hue_order=labels, palette=palette,
        legend=False, width=box_width, linewidth=1, fliersize=0,
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
    ax.tick_params(axis='x', bottom=False, labelbottom=False)
    sns.despine(ax=ax, left=True, bottom=True)
    _annotate_means(ax, df, y_col, labels, box_half_width=box_width / 2)


def _mixed_box_strip(ax, df, y_col, labels, palette, title, ylabel, zero_labels: set[str],
                     box_width=_BOX_WIDTH):
    """Box+strip for subgoal methods; dashed 'always 0' annotation for 0sg baseline."""
    policy_labels = [l for l in labels if l not in zero_labels]
    policy_df = df[df["Method"].isin(policy_labels)]

    sns.boxplot(
        data=policy_df, x="Method", y=y_col,
        order=labels, hue="Method", hue_order=labels, palette=palette, legend=False,
        width=box_width, linewidth=1, fliersize=0,
        ax=ax,
    )
    sns.stripplot(
        data=policy_df, x="Method", y=y_col,
        order=labels, hue="Method", hue_order=labels, palette=palette, legend=False,
        size=3, alpha=0.35, jitter=True,
        ax=ax,
    )
    _annotate_zero(ax, labels, zero_labels, palette)
    ax.set_xlabel("")
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontweight="bold")
    ax.tick_params(axis='x', bottom=False, labelbottom=False)
    sns.despine(ax=ax, left=True, bottom=True)
    _annotate_means(ax, df, y_col, labels, skip_labels=zero_labels, box_half_width=box_width / 2)

# ── Main figure ───────────────────────────────────────────────────────────────

def render(output_path: pathlib.Path = _PDF_PATH) -> None:
    font_family = _register_lm_fonts()
    plt.rcParams.update({
        "font.family": "serif",
        "font.serif":  [font_family, "Palatino", "Times New Roman"],
        "text.usetex": False,
    })
    sns.set_theme(style="whitegrid", font=font_family)

    print("Loading data...")
    labels, colors, palette, methods = _load()

    zero_display = {_METHODS[k][0] for k in ZERO_SUBGOAL_KEYS}

    # Build long-form DataFrames
    term_rows, mk_rows, wt_rows, nr_rows = [], [], [], []
    for m in methods:
        label = m["_label"]
        term_rows.append({"Method": label, "Rate": float(m["terminated"].mean()), "Color": m["_color"]})
        for v in m["makespan"]:
            mk_rows.append({"Method": label, "Makespan (steps)": float(v)})
        for v in m["wall_time"]:
            wt_rows.append({"Method": label, "OMPL Wall Time (s)": float(v)})
        for v in m["n_reached"]:
            nr_rows.append({"Method": label, "Subgoals Reached": int(v)})

    df_mk = pd.DataFrame(mk_rows)
    df_wt = pd.DataFrame(wt_rows)
    df_nr = pd.DataFrame(nr_rows)

    GREY = "#444444"
    fig, axes = plt.subplots(2, 2, figsize=(10, 6),
                             gridspec_kw={'hspace': 0.45, 'wspace': 0.35})
    fig.suptitle("5n1g", fontsize=15, fontweight="bold", y=1.005)

    # ── [0,0] Termination rate ────────────────────────────────────────────────
    ax = axes[0, 0]
    for i, row in enumerate(term_rows):
        r = row["Rate"]
        ax.barh(i, r, color=row["Color"], height=0.5, zorder=3)
        ax.text(r + 0.012, i, f"{r:.0%}", va="center", ha="left",
                fontsize=9.5, color=GREY)
    ax.set_yticks([])
    ax.set_xlim(0, 1.18)
    ax.set_xlabel("Termination rate")
    ax.set_title("Success Rate", fontweight="bold")
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.grid(axis="x", linestyle="--", alpha=0.35, zorder=0)
    sns.despine(ax=ax, left=True, bottom=False)

    # ── [0,1] Makespan — box + strip ─────────────────────────────────────────
    _box_strip(axes[0, 1], df_mk, "Makespan (steps)", labels, palette,
               "Makespan Distribution", "Makespan (steps)")

    # ── [1,0] Wall time — box + strip ────────────────────────────────────────
    _box_strip(axes[1, 0], df_wt, "OMPL Wall Time (s)", labels, palette,
               "OMPL Wall Time", "Wall time (s)")

    # ── [1,1] Subgoals reached — mixed box+strip ──────────────────────────────
    _mixed_box_strip(axes[1, 1], df_nr, "Subgoals Reached", labels, palette,
                     "Subgoals Reached", "Subgoals / episode", zero_display)

    # ── Global legend at bottom ───────────────────────────────────────────────
    from matplotlib.patches import Patch
    legend_handles = [Patch(facecolor=colors[i], edgecolor="#444444", linewidth=0.6)
                      for i in range(len(labels))]
    fig.legend(legend_handles, labels,
               loc="lower center", bbox_to_anchor=(0.5, 0.0),
               ncol=len(labels), frameon=False, fontsize=10)

    plt.tight_layout(rect=[0, 0.06, 1, 1])
    fig.savefig(output_path, bbox_inches="tight", dpi=200)
    print(f"Figure saved → {output_path.absolute()}")
    plt.show()


if __name__ == "__main__":
    render()
