import os
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import pathlib
import numpy as np
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

BASE_PATH = "master_thesis/modules/subgoal_predictor/runs"
OUTPUT_FILE = "training_process.pdf"
BIN_SIZE = 20

# Edit this list to choose which runs appear and in what order.
# Each entry: (subdirectory under BASE_PATH, display label)
RUNS = [
    ("bp_A_20260414_005433",     "bp_A"),
    ("bp_A_ft_20260415_012529",  "ft1"),
    ("bp_A_ft2_20260416_094315", "ft2"),
    ("bp_A_ft3_20260416_235148", "ft3"),
    ("bp_A_ft4_20260419_021501", "ft4"),
    ("bp_A_ft5_20260420_121017", "ft5"),
]

def load_run_data(run_dir, run_name):
    """Loads scalar data from a TensorBoard run directory."""
    ea = EventAccumulator(run_dir)
    ea.Reload()
    
    tags = ea.Tags()['scalars']
    
    metrics = {
        'train/mean_reward': 'Reward',
        'train/frac_terminated': 'Success Rate',
        'train/mean_makespan': 'Makespan',
        'train/mean_plan_wall_time': 'Wall Plan Time'
    }
    
    run_df = None
    for tag, label in metrics.items():
        if tag in tags:
            df = pd.DataFrame(ea.Scalars(tag))
            df = df.rename(columns={'value': label, 'step': 'Step'})
            df = df[['Step', label]]
            
            if run_df is None:
                run_df = df
            else:
                run_df = pd.merge(run_df, df, on='Step', how='outer')
            
    if run_df is not None:
        run_df['Run'] = run_name
        # Sort by step to ensure continuity
        run_df = run_df.sort_values('Step')
        return run_df
    else:
        return pd.DataFrame()

def stitch_runs(runs_config, bin_size=20):
    """
    Stitches multiple runs into a single continuous dataframe.
    Ensures that each run starts at a clean bin boundary to prevent overlap.
    """
    all_data = []
    current_step_offset = 0
    boundaries = []
    
    for path, name in runs_config:
        print(f"Loading {name} from {path}...")
        df = load_run_data(path, name)
        if df.empty:
            continue
            
        # 1. Normalize run steps to start at 0
        min_step = df['Step'].min()
        df['Step'] = df['Step'] - min_step
        
        # 2. Apply offset
        df['Step'] = df['Step'] + current_step_offset
        
        all_data.append(df)
        
        # 3. Calculate next offset aligned to bin grid, no empty strip
        max_step = df['Step'].max()
        last_bin_x = (max_step // bin_size) * bin_size
        next_start = last_bin_x + bin_size
        boundary_pos = last_bin_x + bin_size / 2
        boundaries.append(boundary_pos)

        current_step_offset = next_start
        
    return pd.concat(all_data, ignore_index=True), boundaries[:-1]

def plot_training_process(df, boundaries):
    """Plots the stitched training process with 4 subplots and transition markers."""
    bin_size = 20
    df['Binned Step'] = (df['Step'] // bin_size) * bin_size
    
    sns.set_theme(style="darkgrid")
    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Palatino", "serif"],
    })
    # 3 Subplots in a vertical stack
    fig, axes = plt.subplots(3, 1, figsize=(14, 13), sharex=True)

    plot_configs = [
        ("Success Rate", "Success Rate (Fraction Terminated)", "#457b9d"),
        ("Reward", "Mean Reward", "#e63946"),
        ("Makespan", "Mean Makespan [steps]", "#1d3557")
    ]

    
    for i, (col, ylabel, color) in enumerate(plot_configs):
        ax = axes[i]
        # Using estimator='mean' and errorbar='sd' for the "hull" effect
        sns.lineplot(data=df, x="Binned Step", y=col, hue="Run", ax=ax, 
                     linewidth=2.5, errorbar='sd', legend=(i==0))
        
        ax.set_ylabel(ylabel, fontsize=12, fontweight='bold')
        ax.set_title(f"Training Progress: {col}", fontsize=15, fontweight='bold', pad=12)
        
        # Add vertical dotted lines for run transitions
        for b in boundaries:
            ax.axvline(x=b, color='black', linestyle=':', alpha=0.8, linewidth=2)
            
        if i == 0:
            ax.set_ylim(0, 1.05)
            ax.legend(title="Training Phase", bbox_to_anchor=(1.02, 1), loc='upper left', borderaxespad=0.)

    axes[-1].set_xlabel("Update Step (Stitched & Binned)", fontsize=13, fontweight='bold')
    
    plt.tight_layout()
    
    output_dir = pathlib.Path(__file__).parent
    output_path = output_dir / OUTPUT_FILE
    fig.savefig(output_path, bbox_inches='tight')
    print(f"Plot saved as {output_path.absolute()}")

if __name__ == "__main__":
    full_paths = [(os.path.join(BASE_PATH, p), n) for p, n in RUNS]
    df, boundaries = stitch_runs(full_paths, bin_size=BIN_SIZE)
    if not df.empty:
        plot_training_process(df, boundaries)
    else:
        print("No data found.")
