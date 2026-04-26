"""Scenario A inference comparison — 4-method, 2×2 layout.

All methods achieve near-100% termination on this simple scenario,
so makespan variance is the primary discriminator.

2×2 layout:
  [0,0] Makespan distribution   — box + strip (all episodes)
  [0,1] Failed OMPL plans       — box + strip
  [1,0] OMPL wall time          — box + strip
  [1,1] Mean wait time          — box + strip (0sg always 0)

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
    "A_0sg":    ("No\nSubgoal",        "#999999"),
    "A_mlp":    ("MLP",                "#00b695"),
    "A_hom_gnn":("Homogeneous\nGNN",   "#457b9d"),
    "A_bi_gnn": ("Bipartite\nGNN",     "#e63946"),
}

_PDF_PATH = _DIR / "eval_A_comparison.pdf"

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
        path = candidates[-1]   # most recent / most episodes
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

# ── Panel helper ──────────────────────────────────────────────────────────────

def _box_strip(ax, df, y_col, labels, palette, title, ylabel):
    sns.boxplot(
        data=df, x="Method", y=y_col,
        order=labels, hue="Method", hue_order=labels, palette=palette,
        legend=False, width=0.45, linewidth=1, fliersize=0,
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

    # Build long-form DataFrames
    mk_rows, nf_rows, wt_rows, mw_rows, ss_rows, nr_rows = [], [], [], [], [], []
    for m in methods:
        label = m["_label"]
        for v in m["makespan"]:
            mk_rows.append({"Method": label, "Makespan (steps)": float(v)})
        for v in m["n_failed"]:
            nf_rows.append({"Method": label, "Failed Plans": int(v)})
        for v in m["wall_time"]:
            wt_rows.append({"Method": label, "OMPL Wall Time (s)": float(v)})
        for v in m["mean_wait"]:
            mw_rows.append({"Method": label, "Mean Wait Time (s)": float(v)})
        for v in m["subgoal_spread"]:
            ss_rows.append({"Method": label, "Subgoal Spread (m)": float(v)})
        for v in m["n_reached"]:
            nr_rows.append({"Method": label, "Subgoals Reached": int(v)})

    df_mk = pd.DataFrame(mk_rows)
    df_nf = pd.DataFrame(nf_rows)
    df_wt = pd.DataFrame(wt_rows)
    df_mw = pd.DataFrame(mw_rows)
    df_ss = pd.DataFrame(ss_rows)
    df_nr = pd.DataFrame(nr_rows)

    fig, axes = plt.subplots(2, 3, figsize=(16, 9))
    fig.subplots_adjust(hspace=0.38, wspace=0.28)

    _box_strip(axes[0, 0], df_mk, "Makespan (steps)", labels, palette,
               "Makespan Distribution", "Makespan (steps)")

    _box_strip(axes[0, 1], df_nf, "Failed Plans", labels, palette,
               "Failed OMPL Plans", "Failed plans / episode")

    _box_strip(axes[0, 2], df_wt, "OMPL Wall Time (s)", labels, palette,
               "OMPL Wall Time", "Wall time (s)")

    _box_strip(axes[1, 0], df_mw, "Mean Wait Time (s)", labels, palette,
               "Mean Prescribed Wait Time", "Mean wait (s)")

    _box_strip(axes[1, 1], df_ss, "Subgoal Spread (m)", labels, palette,
               "Subgoal Spatial Spread\n(mean pairwise distance)", "Spread (m)")

    _box_strip(axes[1, 2], df_nr, "Subgoals Reached", labels, palette,
               "Subgoals Reached", "Subgoals / episode")

    plt.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    print(f"Figure saved → {output_path.absolute()}")
    plt.show()


if __name__ == "__main__":
    render()
