import os
import pathlib
import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

BASE_PATH = "master_thesis/modules/subgoal_predictor/runs/homogeneous_gnn/pre_030426"
OUTPUT_FILE = "algo_comparison.pdf"
SMOOTH_WINDOW = 20

RUNS = {
    "PPO":       (f"{BASE_PATH}/stage1b_20260324_103903", "#457b9d"),
    "REINFORCE": (f"{BASE_PATH}/stage1a_20260325_210707", "#e63946"),
}

METRICS = {
    "train/frac_terminated": ("Success Rate",     "Fraction Terminated",  (0, 1.05)),
    "train/mean_reward":     ("Mean Reward",       "Mean Episode Reward",  None),
    "train/mean_entropy":    ("Policy Entropy",    "Entropy [nats]",       None),
}


def load_scalars(run_dir: str, tag: str) -> pd.DataFrame:
    ea = EventAccumulator(run_dir)
    ea.Reload()
    events = ea.Scalars(tag)
    return pd.DataFrame({"step": [e.step for e in events], "value": [e.value for e in events]})


def smooth(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, center=True, min_periods=1).mean()


def main():
    sns.set_theme(style="darkgrid")
    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Palatino", "serif"],
    })

    fig, axes = plt.subplots(1, 3, figsize=(14, 4), sharey=False)

    for ax, (tag, (title, ylabel, ylim)) in zip(axes, METRICS.items()):
        for label, (run_dir, color) in RUNS.items():
            df = load_scalars(run_dir, tag)
            ax.plot(df["step"], df["value"], color=color, alpha=0.15, linewidth=0.8)
            ax.plot(df["step"], smooth(df["value"], SMOOTH_WINDOW),
                    color=color, linewidth=2.2, label=label)

        ax.set_title(title, fontsize=13, fontweight="bold", pad=10)
        ax.set_xlabel("Training Update", fontsize=11)
        ax.set_ylabel(ylabel, fontsize=11)
        if ylim:
            ax.set_ylim(*ylim)

    axes[0].legend(fontsize=11, framealpha=0.85)

    plt.tight_layout()

    output_path = pathlib.Path(__file__).parent / OUTPUT_FILE
    fig.savefig(output_path, bbox_inches="tight")
    print(f"Saved: {output_path.absolute()}")


if __name__ == "__main__":
    main()
