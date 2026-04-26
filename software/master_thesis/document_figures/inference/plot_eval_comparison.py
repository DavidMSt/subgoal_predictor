import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

b = np.load('master_thesis/modules/subgoal_predictor/results/eval_baseline_100ep.npz')
p = np.load('master_thesis/modules/subgoal_predictor/results/eval_policy_100ep.npz')

COLOR_B = '#4C72B0'   # blue  — baseline (0 subgoals)
COLOR_P = '#DD8452'   # orange — policy (1 subgoal)
ALPHA   = 0.65
MAX_STEPS = 450

fig, axes = plt.subplots(2, 3, figsize=(14, 8))
fig.suptitle('Evaluation: 0-Subgoal Baseline vs. Trained Policy (100 episodes each)',
             fontsize=13, fontweight='bold', y=1.01)

# ── 1. Termination (bar) ──────────────────────────────────────────────────────
ax = axes[0, 0]
vals = [b['terminated'].mean(), p['terminated'].mean()]
bars = ax.bar(['Baseline\n(0 SG)', 'Policy\n(1 SG)'], vals,
              color=[COLOR_B, COLOR_P], width=0.4)
ax.set_ylim(0, 1.05)
ax.set_ylabel('Fraction terminated')
ax.set_title('Termination rate')
ax.yaxis.set_major_formatter(ticker.PercentFormatter(xmax=1))
for bar, v in zip(bars, vals):
    ax.text(bar.get_x() + bar.get_width()/2, v + 0.02, f'{v:.1%}',
            ha='center', va='bottom', fontsize=10)

# ── 2. Makespan histogram (terminated episodes only) ─────────────────────────
ax = axes[0, 1]
bm = b['makespan'][b['terminated']]
pm = p['makespan'][p['terminated']]
bins = np.linspace(0, MAX_STEPS, 25)
ax.hist(bm, bins=bins, density=True, alpha=ALPHA, color=COLOR_B, label=f'Baseline  (μ={bm.mean():.0f})')
ax.hist(pm, bins=bins, density=True, alpha=ALPHA, color=COLOR_P, label=f'Policy    (μ={pm.mean():.0f})')
ax.axvline(bm.mean(), color=COLOR_B, linestyle='--', linewidth=1.2)
ax.axvline(pm.mean(), color=COLOR_P, linestyle='--', linewidth=1.2)
ax.set_xlabel('Makespan (steps)')
ax.set_ylabel('Density')
ax.set_title('Makespan (terminated episodes)')
ax.legend(fontsize=9)

# ── 3. Failed plans PMF ───────────────────────────────────────────────────────
ax = axes[0, 2]
max_f = int(max(b['n_failed'].max(), p['n_failed'].max()))
bins_f = np.arange(0, max_f + 2) - 0.5
ax.hist(b['n_failed'], bins=bins_f, density=True, alpha=ALPHA, color=COLOR_B,
        label=f'Baseline  (μ={b["n_failed"].mean():.1f})')
ax.hist(p['n_failed'], bins=bins_f, density=True, alpha=ALPHA, color=COLOR_P,
        label=f'Policy    (μ={p["n_failed"].mean():.1f})')
ax.set_xlabel('Failed OMPL plans per episode')
ax.set_ylabel('Probability')
ax.set_title('Failed plans')
ax.legend(fontsize=9)

# ── 4. Wall plan time histogram ───────────────────────────────────────────────
ax = axes[1, 0]
bins_w = np.linspace(0, max(b['wall_time'].max(), p['wall_time'].max()) * 1.05, 25)
ax.hist(b['wall_time'], bins=bins_w, density=True, alpha=ALPHA, color=COLOR_B,
        label=f'Baseline  (μ={b["wall_time"].mean():.1f}s)')
ax.hist(p['wall_time'], bins=bins_w, density=True, alpha=ALPHA, color=COLOR_P,
        label=f'Policy    (μ={p["wall_time"].mean():.1f}s)')
ax.axvline(b['wall_time'].mean(), color=COLOR_B, linestyle='--', linewidth=1.2)
ax.axvline(p['wall_time'].mean(), color=COLOR_P, linestyle='--', linewidth=1.2)
ax.set_xlabel('Total OMPL wall time (s)')
ax.set_ylabel('Density')
ax.set_title('Planning wall time\n(sequential; decentralised = max per agent)')
ax.legend(fontsize=9)

# ── 5. Reached subgoals PMF ───────────────────────────────────────────────────
ax = axes[1, 1]
max_r = int(max(b['n_reached'].max(), p['n_reached'].max()))
bins_r = np.arange(0, max_r + 2) - 0.5
ax.hist(b['n_reached'], bins=bins_r, density=True, alpha=ALPHA, color=COLOR_B,
        label=f'Baseline  (μ={b["n_reached"].mean():.2f})')
ax.hist(p['n_reached'], bins=bins_r, density=True, alpha=ALPHA, color=COLOR_P,
        label=f'Policy    (μ={p["n_reached"].mean():.2f})')
ax.set_xlabel('Subgoals reached per episode')
ax.set_ylabel('Probability')
ax.set_title('Subgoals reached')
ax.legend(fontsize=9)

# ── 6. Wait spread histogram ──────────────────────────────────────────────────
ax = axes[1, 2]
pw = p['wait_spread'][p['wait_spread'] > 0]
if len(pw) > 0:
    ax.hist(pw, bins=20, density=True, alpha=ALPHA, color=COLOR_P,
            label=f'Policy  (μ={p["wait_spread"].mean():.2f}s)')
    ax.axvline(pw.mean(), color=COLOR_P, linestyle='--', linewidth=1.2)
ax.axvline(0, color=COLOR_B, linewidth=2, label='Baseline (always 0)')
ax.set_xlabel('Wait time spread across agents (s)')
ax.set_ylabel('Density')
ax.set_title('Wait spread\n(temporal staggering)')
ax.legend(fontsize=9)

plt.tight_layout()
plt.savefig('master_thesis/modules/subgoal_predictor/results/eval_comparison.pdf',
            bbox_inches='tight')
plt.savefig('master_thesis/modules/subgoal_predictor/results/eval_comparison.png',
            dpi=150, bbox_inches='tight')
print("Saved eval_comparison.pdf and .png")
plt.show()
