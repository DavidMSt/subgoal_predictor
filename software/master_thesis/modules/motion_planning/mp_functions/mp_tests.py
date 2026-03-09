import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import matplotlib.transforms as mtransforms

from master_thesis.modules.motion_planning.mp_functions.ompl_planner import (
    OMPLSmoothPathPlanner, OMPLPlannerConfig, RoadmapBuilder,
)
from master_thesis.modules.motion_planning.mp_functions.opt_safe import Plotter

# ── Shared scenario ────────────────────────────────────────────────────────────
limits = ((0.0, 3.0), (-1.0, 1.0))

obstacles = [
    dict(x=2.5,  y=-0.5,  length=1.0, width=0.05, height=0.11, psi=-np.pi    ),
    dict(x=1.5,  y=-0.5,  length=1.0, width=0.05, height=0.11, psi=-np.pi/2  ),
    dict(x=0.5,  y=-0.25, length=0.5, width=0.05, height=0.11, psi=-np.pi/2  ),
    dict(x=0.75, y=-0.5,  length=0.5, width=0.05, height=0.11, psi=0.0       ),
    dict(x=1.0,  y=0.5,   length=1.0, width=0.05, height=0.11, psi=np.pi/2   ),
    dict(x=0.25, y=-0.5,  length=0.5, width=0.05, height=0.11, psi=-np.pi    ),
    dict(x=2.5,  y=0.0,   length=1.0, width=0.05, height=0.11, psi=0.0       ),
    dict(x=1.75, y=0.75,  length=0.5, width=0.05, height=0.11, psi=-np.pi/2  ),
]

FRODO_DIMS = (0.157, 0.115, 0.11)  # L, W, H

CFG = OMPLPlannerConfig(
    Ts=0.1,
    v_max=0.5,
    psi_dot_max=np.pi / 3,
    timelimit=10.0,
    roadmap_time=5.0,
)


# ── Shared plot helpers ────────────────────────────────────────────────────────

def _draw_obstacles(ax):
    for obs in obstacles:
        rect = Rectangle(
            (-obs['length'] / 2, -obs['width'] / 2),
            obs['length'], obs['width'],
            linewidth=1, edgecolor='k', facecolor='#888888', alpha=0.6,
        )
        t = mtransforms.Affine2D().rotate(obs['psi']).translate(obs['x'], obs['y']) + ax.transData
        rect.set_transform(t)
        ax.add_patch(rect)


def _plot_trajectory(ax, states, start, goal, color='tab:blue', label=None):
    ax.plot(states[:, 0], states[:, 1], '-', color=color, lw=1.5, label=label, zorder=4)
    ax.plot(*start[:2], 'o', color=color, ms=8, zorder=5)
    ax.plot(*goal[:2],  '*', color=color, ms=10, zorder=5)


def _plot_controls(ax, actions, dt, title='Control inputs'):
    t = np.arange(len(actions) + 1) * dt
    ax.set_title(title)
    ax.step(t[:-1], actions[:, 0], where='post', label='v [m/s]')
    ax.step(t[:-1], actions[:, 1], where='post', label='ψ̇ [rad/s]')
    ax.set_xlabel('time [s]')
    ax.legend()
    ax.grid(True, alpha=0.3)


# ── Test: single RRT solve ─────────────────────────────────────────────────────

def test_rrt():
    start = np.array([0.25,  0.75, 0.0])
    goal  = np.array([2.75, -0.75, 0.0])

    planner = OMPLSmoothPathPlanner(
        limits=limits, obstacles=obstacles, agent_dims=FRODO_DIMS, config=CFG,
    )

    solved, length = planner.solve(start, goal)
    if not solved:
        print("Planning failed")
        raise SystemExit(1)

    solution = planner.get_solution()
    states  = np.array(solution['states'])
    actions = np.array(solution['inputs'])
    dt      = solution['dt']

    print(f"RRT  solved  length={length:.3f} m  steps={len(actions)}  T={len(actions)*dt:.2f} s")
    print(f"  v  [{actions[:,0].min():.3f}, {actions[:,0].max():.3f}] m/s")
    print(f"  ψ̇  [{actions[:,1].min():.3f}, {actions[:,1].max():.3f}] rad/s")

    opt = planner._opt
    fig, (ax_path, ax_ctrl) = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle('RRT — single query')

    ax_path.set_aspect('equal')
    ax_path.grid(True, alpha=0.3)
    Plotter.assignment04_plot(ax_path, opt.setup, opt.curve_function_segments, opt.hyperplanes)
    _plot_trajectory(ax_path, states, start, goal)
    ax_path.set_title('Planned trajectory')
    ax_path.legend(['trajectory', 'start', 'goal'])

    _plot_controls(ax_ctrl, actions, dt, 'Control inputs')

    plt.tight_layout()
    plt.show()


# ── Test: PRM* roadmap + multi-query ──────────────────────────────────────────

def test_prm():
    from ompl import base as ob

    queries = [
        (np.array([0.25,  0.75, 0.0]), np.array([2.75, -0.75, 0.0])),
        (np.array([0.25, -0.75, 0.0]), np.array([2.75,  0.75, 0.0])),
    ]
    colors = ['tab:blue', 'tab:red']

    print("Building PRM* roadmap ...")
    builder = RoadmapBuilder(limits=limits, obstacles=obstacles,
                             agent_dims=FRODO_DIMS, config=CFG)
    prm = builder.build()

    # ── Extract graph ──────────────────────────────────────────────
    pd = ob.PlannerData(prm.si)
    prm.prm.getPlannerData(pd)
    n = pd.numVertices()

    vx, vy = [], []
    for i in range(n):
        s = pd.getVertex(i).getState()
        vx.append(s.getX())
        vy.append(s.getY())

    edge_set = set()
    for i in range(n):
        try:
            neighbors = ob.vectorUint()
            pd.getEdges(i, neighbors)
            for j in neighbors:
                edge_set.add((min(i, j), max(i, j)))
        except Exception:
            break

    print(f"Roadmap: {n} nodes, {len(edge_set)} edges")

    # ── Layout ────────────────────────────────────────────────────
    n_cols = 1 + len(queries)
    fig, axes = plt.subplots(1, n_cols, figsize=(6 * n_cols, 5))
    fig.suptitle('PRM* — roadmap + multi-query')

    ax_map = axes[0]
    ax_map.set_title(f'Roadmap  ({n} nodes, {len(edge_set)} edges)')
    ax_map.set_aspect('equal')
    ax_map.set_xlim(limits[0])
    ax_map.set_ylim(limits[1])
    ax_map.grid(True, alpha=0.3)

    _draw_obstacles(ax_map)

    for i, j in edge_set:
        ax_map.plot([vx[i], vx[j]], [vy[i], vy[j]],
                    'k-', lw=0.4, alpha=0.2, zorder=1)
    ax_map.scatter(vx, vy, s=6, c='#555555', zorder=2)

    # ── Queries ───────────────────────────────────────────────────
    planner = builder._planner
    for idx, ((s_arr, g_arr), color) in enumerate(zip(queries, colors)):
        ax_ctrl = axes[1 + idx]

        solved, length = planner.solve(s_arr, g_arr, roadmap=prm)
        if not solved:
            print(f"Query {idx + 1}: failed")
            ax_ctrl.set_title(f'Query {idx + 1} — FAILED')
            continue

        sol     = planner.get_solution()
        states  = np.array(sol['states'])
        actions = np.array(sol['inputs'])
        dt      = sol['dt']

        print(f"Query {idx + 1}: solved  length={length:.3f} m  "
              f"steps={len(actions)}  T={len(actions)*dt:.2f} s")

        _plot_trajectory(ax_map, states, s_arr, g_arr, color=color, label=f'Q{idx + 1}')
        _plot_controls(ax_ctrl, actions, dt, f'Query {idx + 1} — control inputs')

    ax_map.legend()
    plt.tight_layout()
    plt.show()


# ── Entry point  (switch MODE to select which test runs) ──────────────────────
MODE = 'prm'   # 'rrt'  |  'prm'

if __name__ == '__main__':
    if MODE == 'prm':
        test_prm()
    else:
        test_rrt()
