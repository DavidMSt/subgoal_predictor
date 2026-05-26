"""Presentation-sized inference plots — fewer panels for slides.

Scenario A:  1×2  — Makespan Distribution | Subgoals Reached
Scenario C:  1×3  — Success Rate | Makespan Distribution | Gap Crossings
Scenario D:  1×3  — Success Rate | Makespan Distribution | Gap Crossings

Run from repo root:
    python -m master_thesis.document_figures.inference.plot_presentation
"""

import pathlib
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import seaborn as sns

# ── Configuration ─────────────────────────────────────────────────────────────

_DIR = pathlib.Path(__file__).parent

_METHODS_A: dict[str, tuple[str, str]] = {
    "A_0sg":     ("No Subgoal",      "#a8dadc"),
    "A_mlp":     ("MLP",             "#457b9d"),
    "A_hom_gnn": ("Homogeneous GNN", "#00b695"),
    "A_bi_gnn":  ("Bipartite GNN",   "#e63946"),
}
ZERO_SUBGOAL_KEYS_A = {"A_0sg"}

_SCENARIOS_CD: dict[str, dict] = {
    "C": {
        "methods": {
            "C_0sg":    ("No Subgoal",    "#a8dadc"),
            "C_bi_gnn": ("Bipartite GNN", "#e63946"),
        },
        "zero_subgoal_keys": {"C_0sg"},
        "output": _DIR / "eval_C_presentation.pdf",
    },
    "D": {
        "methods": {
            "D_0sg":    ("No Subgoal",    "#a8dadc"),
            "D_bi_gnn": ("Bipartite GNN", "#e63946"),
        },
        "zero_subgoal_keys": {"D_0sg"},
        "output": _DIR / "eval_D_presentation.pdf",
    },
}

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

def _load_key(key: str, label: str, color: str) -> dict:
    candidates = sorted(_DIR.glob(f"eval_{key}_*.npz"))
    if not candidates:
        raise FileNotFoundError(f"No npz found for '{key}' in {_DIR}")
    d = dict(np.load(candidates[-1]))
    d["_label"] = label
    d["_color"] = color
    n    = len(d["terminated"])
    term = d["terminated"].mean()
    print(f"  {key:15s}  n={n}  term={term:.0%}  "
          f"makespan_mean={d['makespan'].mean():.0f}  "
          f"makespan_std={d['makespan'].std():.0f}")
    return d

# ── Panel helpers ─────────────────────────────────────────────────────────────

def _annotate_medians(ax, df, y_col, labels, skip_labels=None, box_half_width=None):
    if box_half_width is None:
        box_half_width = _BOX_WIDTH / 2
    skip_labels = skip_labels or set()
    for i, label in enumerate(labels):
        if label in skip_labels:
            continue
        vals = df[df["Method"] == label][y_col].dropna()
        if len(vals) == 0:
            continue
        median_val = float(vals.median())
        ax.text(
            i + box_half_width + 0.06, median_val, f"{median_val:.1f}",
            ha="left", va="center", fontsize=7.5,
            color="#222222", fontweight="bold",
        )


def _annotate_zero(ax, labels, zero_labels, palette):
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
            fontsize=8.5, color=color, zorder=6,
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
    ax.set_title(title)
    ax.tick_params(axis='x', bottom=False, labelbottom=False)
    sns.despine(ax=ax, left=True, bottom=True)
    _annotate_medians(ax, df, y_col, labels, box_half_width=box_width / 2)


def _mixed_box_strip(ax, df, y_col, labels, palette, title, ylabel, zero_labels: set[str],
                     box_width=_BOX_WIDTH):
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
    ax.set_title(title)
    ax.tick_params(axis='x', bottom=False, labelbottom=False)
    sns.despine(ax=ax, left=True, bottom=True)
    _annotate_medians(ax, df, y_col, labels, skip_labels=zero_labels, box_half_width=box_width / 2)


def _success_rate_bar(ax, term_rows, labels, title="Success Rate"):
    GREY = "#444444"
    for i, row in enumerate(term_rows):
        r = row["Rate"]
        ax.barh(i, r, color=row["Color"], height=0.5, zorder=3)
        ax.text(r + 0.012, i, f"{r:.0%}", va="center", ha="left",
                fontsize=9.5, color=GREY)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels([""] * len(labels))
    ax.invert_yaxis()
    ax.set_xlim(0, 1.18)
    ax.set_xlabel("Termination rate")
    ax.set_title(title)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.grid(axis="x", linestyle="--", alpha=0.35, zorder=0)
    sns.despine(ax=ax, left=True, bottom=False)

# ── Scenario A (1×2) ──────────────────────────────────────────────────────────

def render_A(font_family: str, output_path: pathlib.Path = _DIR / "eval_A_presentation.pdf") -> None:
    print("\nLoading A data...")
    methods = []
    for key, (label, color) in _METHODS_A.items():
        d = _load_key(key, label, color)
        methods.append(d)

    labels  = [m["_label"] for m in methods]
    colors  = [m["_color"] for m in methods]
    palette = dict(zip(labels, colors))
    zero_display = {_METHODS_A[k][0] for k in ZERO_SUBGOAL_KEYS_A}

    mk_rows, nr_rows = [], []
    for m in methods:
        label = m["_label"]
        for v in m["makespan"]:
            mk_rows.append({"Method": label, "Makespan (steps)": float(v)})
        for v in m["n_reached"]:
            nr_rows.append({"Method": label, "Subgoals Reached": int(v)})

    df_mk = pd.DataFrame(mk_rows)
    df_nr = pd.DataFrame(nr_rows)

    fig, axes = plt.subplots(1, 2, figsize=(9, 4),
                             gridspec_kw={'wspace': 0.35})

    _box_strip(axes[0], df_mk, "Makespan (steps)", labels, palette,
               "Makespan Distribution", "Makespan (steps)")

    _mixed_box_strip(axes[1], df_nr, "Subgoals Reached", labels, palette,
                     "Subgoals Reached", "Subgoals / episode", zero_display)

    from matplotlib.patches import Patch
    legend_handles = [Patch(facecolor=colors[i], edgecolor="#444444", linewidth=0.6)
                      for i in range(len(labels))]
    fig.legend(legend_handles, labels,
               loc="lower center", bbox_to_anchor=(0.5, 0.0),
               ncol=len(labels), frameon=False, fontsize=10)

    plt.tight_layout(rect=[0, 0.1, 1, 1])
    fig.savefig(output_path, bbox_inches="tight", dpi=200)
    print(f"Figure saved → {output_path.absolute()}")
    plt.show()

# ── Scenarios C / D (1×3) ─────────────────────────────────────────────────────

def render_CD(scenario_key: str, font_family: str) -> None:
    cfg = _SCENARIOS_CD[scenario_key]
    methods_cfg = cfg["methods"]
    zero_keys   = cfg["zero_subgoal_keys"]
    output_path = cfg["output"]

    print(f"\nLoading {scenario_key} data...")
    methods = [_load_key(k, label, color) for k, (label, color) in methods_cfg.items()]

    labels  = [m["_label"] for m in methods]
    colors  = [m["_color"] for m in methods]
    palette = dict(zip(labels, colors))
    zero_display = {methods_cfg[k][0] for k in zero_keys}

    term_rows, mk_rows, nc_rows = [], [], []
    for m in methods:
        term  = m["terminated"].astype(bool)
        label = m["_label"]
        term_rows.append({"Method": label, "Rate": float(term.mean()), "Color": m["_color"]})
        for v in m["makespan"][term]:
            mk_rows.append({"Method": label, "Makespan (steps)": float(v)})
        for v in m["n_crossed"]:
            nc_rows.append({"Method": label, "Gap Crossings": int(v)})

    df_mk = pd.DataFrame(mk_rows)
    df_nc = pd.DataFrame(nc_rows)

    fig, axes = plt.subplots(1, 3, figsize=(12, 4),
                             gridspec_kw={'wspace': 0.35})

    _success_rate_bar(axes[0], term_rows, labels)

    _box_strip(axes[1], df_mk, "Makespan (steps)", labels, palette,
               "Makespan Distribution\n(terminated episodes only)", "Makespan (steps)")

    _box_strip(axes[2], df_nc, "Gap Crossings", labels, palette,
               "Gap Crossings", "Crossings / episode")

    from matplotlib.patches import Patch
    legend_handles = [Patch(facecolor=color, label=label)
                      for label, color in zip(labels, colors)]
    fig.legend(handles=legend_handles, loc="lower center", bbox_to_anchor=(0.5, 0.0),
               ncol=len(labels), frameon=False, fontsize=10)

    plt.tight_layout(rect=[0, 0.1, 1, 1])
    fig.savefig(output_path, bbox_inches="tight", dpi=200)
    print(f"Figure saved → {output_path.absolute()}")
    plt.show()

# ── Entry point ───────────────────────────────────────────────────────────────

def render() -> None:
    font_family = _register_lm_fonts()
    plt.rcParams.update({
        "font.family":    "serif",
        "font.serif":     [font_family, "Palatino", "Times New Roman"],
        "text.usetex":    False,
        "axes.titlesize": 13,
        "axes.labelsize": 10,
    })
    sns.set_theme(style="whitegrid", font=font_family)

    render_A(font_family)
    render_CD("C", font_family)
    render_CD("D", font_family)


if __name__ == "__main__":
    render()
