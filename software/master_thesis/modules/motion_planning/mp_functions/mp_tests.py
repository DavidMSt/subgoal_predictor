import time
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

# ── 4×4 maze scenario ─────────────────────────────────────────────────────────
MAZE_LIMITS = ((-2.0, 2.0), (-2.0, 2.0))

MAZE_OBSTACLES = [
    # Outer boundary
    dict(x= 0.0, y= 2.0, length=4.0, width=0.1, height=1.0, psi=0.0),
    dict(x= 0.0, y=-2.0, length=4.0, width=0.1, height=1.0, psi=0.0),
    dict(x=-2.0, y= 0.0, length=4.0, width=0.1, height=1.0, psi=1.5708),
    dict(x= 2.0, y= 0.0, length=4.0, width=0.1, height=1.0, psi=1.5708),
    # Top row (y=1.5)
    dict(x=-1.25, y= 1.5, length=1.0, width=0.1, height=1.0, psi=1.5708),
    dict(x= 0.0,  y= 1.5, length=1.0, width=0.1, height=1.0, psi=0.0),
    dict(x= 1.25, y= 1.5, length=1.0, width=0.1, height=1.0, psi=1.5708),
    # Upper-middle row (y=0.75)
    dict(x=-1.5,  y= 0.75, length=0.5, width=0.1, height=1.0, psi=0.0),
    dict(x=-0.5,  y= 0.75, length=1.0, width=0.1, height=1.0, psi=1.5708),
    dict(x= 0.5,  y= 0.75, length=1.0, width=0.1, height=1.0, psi=0.0),
    dict(x= 1.5,  y= 0.75, length=1.0, width=0.1, height=1.0, psi=1.5708),
    # Center row (y=0.0)
    dict(x=-1.0,  y= 0.0, length=1.0, width=0.1, height=1.0, psi=1.5708),
    dict(x= 0.0,  y= 0.0, length=1.0, width=0.1, height=1.0, psi=0.0),
    dict(x= 1.0,  y= 0.0, length=1.0, width=0.1, height=1.0, psi=1.5708),
    # Lower-middle row (y=-0.75)
    dict(x=-1.5,  y=-0.75, length=1.0, width=0.1, height=1.0, psi=1.5708),
    dict(x=-0.5,  y=-0.75, length=1.0, width=0.1, height=1.0, psi=0.0),
    dict(x= 0.5,  y=-0.75, length=1.0, width=0.1, height=1.0, psi=1.5708),
    dict(x= 1.5,  y=-0.75, length=0.5, width=0.1, height=1.0, psi=0.0),
    # Bottom row (y=-1.5)
    dict(x=-1.25, y=-1.5, length=1.0, width=0.1, height=1.0, psi=1.5708),
    dict(x= 0.0,  y=-1.5, length=1.0, width=0.1, height=1.0, psi=0.0),
    dict(x= 1.25, y=-1.5, length=1.0, width=0.1, height=1.0, psi=1.5708),
]

MAZE_QUERIES = [
    # (name, start [x,y,psi], goal [x,y,psi])
    ('Agent 1', np.array([-1.75,  1.75, 0.0]), np.array([-1.75, -1.75, 0.0])),
    ('Agent 2', np.array([ 0.0,   1.75, 0.0]), np.array([ 0.0,  -1.75, 0.0])),
    ('Agent 3', np.array([ 1.75,  1.75, 0.0]), np.array([ 1.75, -1.75, 0.0])),
]
MAZE_COLORS = ['tab:blue', 'tab:orange', 'tab:green']

MAZE_CFG = OMPLPlannerConfig(
    Ts=0.1,
    v_max=0.5,
    psi_dot_max=np.pi / 3,
    timelimit=30.0,
    query_timelimit=0.1,   # dense roadmap → connection + A* needs only a few new nodes
    roadmap_time=120.0,
)


# ── Timed planner (test-only subclass) ────────────────────────────────────────

_MAX_RETRIES = 5   # mirror OMPLTrajectoryPlanner._MAX_BEZIER_RETRIES


class _TimedPlanner(OMPLSmoothPathPlanner):
    """Thin subclass that records per-phase wall-clock times during solve().

    Attributes set after each solve():
        t_ompl        – cumulative seconds in OMPL across all attempts
        t_bezier      – cumulative seconds in Bézier across all attempts
        n_attempts    – number of solve() calls made
        fail_reason   – 'ompl_timeout' | 'bezier_infeasible' | None (success)
    """

    t_ompl:      float = 0.0
    t_bezier:    float = 0.0
    n_attempts:  int   = 0
    fail_reason: str | None = None

    def _solve_rrt(self, pdef) -> bool:
        t0 = time.perf_counter()
        result = super()._solve_rrt(pdef)
        self.t_ompl += time.perf_counter() - t0
        return result

    def _query_roadmap(self, prm, pdef, si) -> bool:
        t0 = time.perf_counter()
        result = super()._query_roadmap(prm, pdef, si)
        self.t_ompl += time.perf_counter() - t0
        return result

    def _run_bezier_pipeline(self, waypoints, start, goal) -> bool:
        t0 = time.perf_counter()
        result = super()._run_bezier_pipeline(waypoints, start, goal)
        self.t_bezier += time.perf_counter() - t0
        return result

    def solve_with_retries(
        self, start, goal, roadmap=None
    ) -> tuple[bool, float]:
        """Retry loop matching OMPLTrajectoryPlanner._MAX_BEZIER_RETRIES logic."""
        self.t_ompl = self.t_bezier = 0.0
        self.n_attempts = 0
        self.fail_reason = None
        active_roadmap = roadmap

        for attempt in range(_MAX_RETRIES):
            self.n_attempts += 1
            solved, length = self.solve(start, goal, roadmap=active_roadmap)
            if solved:
                return True, length

            opt = getattr(self, '_opt', None)
            if opt is not None and not opt.feasible:
                # Bézier failed — try again with a new RRT path
                if active_roadmap is not None:
                    active_roadmap = None   # fall back to RRT once
                self.fail_reason = 'bezier_infeasible'
            else:
                # OMPL couldn't find any geometric path — no point retrying
                self.fail_reason = 'ompl_timeout'
                return False, 0.0

        return False, 0.0


# ── Shared plot helpers ────────────────────────────────────────────────────────

def _draw_maze_obstacles(ax):
    for obs in MAZE_OBSTACLES:
        rect = Rectangle(
            (-obs['length'] / 2, -obs['width'] / 2),
            obs['length'], obs['width'],
            linewidth=1, edgecolor='k', facecolor='#888888', alpha=0.6,
        )
        t = mtransforms.Affine2D().rotate(obs['psi']).translate(obs['x'], obs['y']) + ax.transData
        rect.set_transform(t)
        ax.add_patch(rect)


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


# ── Test: RRT vs PRM* benchmark on 4×4 maze (3 agents) ───────────────────────

def test_benchmark():
    """Compare RRT and PRM* (2-min roadmap) on the maze_4x4 scenario.

    Measures:
      - OMPL search time   (RRT solve / PRM* A* query)
      - Bézier optimisation time
      - Total planning time per agent
      - Roadmap build time (amortised across all agents)
    Saves two figures: trajectory comparison + timing bar chart.
    """
    import os

    out_dir = '/tmp/mp_benchmark'
    os.makedirs(out_dir, exist_ok=True)

    # ── Shared planner factory ────────────────────────────────────────
    def _make_planner():
        return _TimedPlanner(
            limits=MAZE_LIMITS,
            obstacles=MAZE_OBSTACLES,
            agent_dims=FRODO_DIMS,
            config=MAZE_CFG,
        )

    # ── RRT baseline ─────────────────────────────────────────────────
    print('=' * 60)
    print('RRT baseline (one planner per agent, independent solves)')
    print('=' * 60)

    rrt_results = []
    for name, start, goal in MAZE_QUERIES:
        planner = _make_planner()
        t_wall0 = time.perf_counter()
        solved, length = planner.solve_with_retries(start, goal)
        t_wall = time.perf_counter() - t_wall0

        if not solved:
            print(f'  {name}: FAILED  reason={planner.fail_reason}  attempts={planner.n_attempts}')
            rrt_results.append(None)
            continue

        sol = planner.get_solution()
        rrt_results.append({
            'name': name, 'start': start, 'goal': goal,
            'states': np.array(sol['states']),
            'inputs': np.array(sol['inputs']),
            'dt': sol['dt'],
            'length': length,
            't_ompl': planner.t_ompl,
            't_bezier': planner.t_bezier,
            't_total': t_wall,
            'n_attempts': planner.n_attempts,
        })
        r = rrt_results[-1]
        print(f'  {name}: length={length:.3f} m  steps={len(r["inputs"])}'
              f'  ompl={r["t_ompl"]:.2f}s  bezier={r["t_bezier"]:.2f}s'
              f'  total={r["t_total"]:.2f}s  attempts={r["n_attempts"]}')

    # ── PRM* with 2-minute roadmap ────────────────────────────────────
    print()
    print('=' * 60)
    print(f'PRM*  roadmap_time={MAZE_CFG.roadmap_time:.0f}s  query_timelimit={MAZE_CFG.query_timelimit:.1f}s')
    print('=' * 60)

    print('Building roadmap ...')
    prm_planner = _make_planner()
    t_build0 = time.perf_counter()
    roadmap = prm_planner.build_roadmap()
    t_build = time.perf_counter() - t_build0
    print(f'  Roadmap built in {t_build:.1f}s')

    prm_results = []
    for name, start, goal in MAZE_QUERIES:
        t_wall0 = time.perf_counter()
        solved, length = prm_planner.solve_with_retries(start, goal, roadmap=roadmap)
        t_wall = time.perf_counter() - t_wall0

        if not solved:
            print(f'  {name}: FAILED  reason={prm_planner.fail_reason}  attempts={prm_planner.n_attempts}')
            prm_results.append(None)
            continue

        sol = prm_planner.get_solution()
        prm_results.append({
            'name': name, 'start': start, 'goal': goal,
            'states': np.array(sol['states']),
            'inputs': np.array(sol['inputs']),
            'dt': sol['dt'],
            'length': length,
            't_ompl': prm_planner.t_ompl,
            't_bezier': prm_planner.t_bezier,
            't_total': t_wall,
            'n_attempts': prm_planner.n_attempts,
        })
        r = prm_results[-1]
        print(f'  {name}: length={length:.3f} m  steps={len(r["inputs"])}'
              f'  ompl={r["t_ompl"]:.3f}s  bezier={r["t_bezier"]:.2f}s'
              f'  total={r["t_total"]:.2f}s  attempts={r["n_attempts"]}')

    print()
    t_prm_total   = sum(r['t_total'] for r in prm_results if r) + t_build
    t_rrt_total   = sum(r['t_total'] for r in rrt_results if r)
    t_prm_queries = sum(r['t_total'] for r in prm_results if r)
    n_rrt_ok = sum(1 for r in rrt_results if r)
    print(f'RRT total ({n_rrt_ok}/3 succeeded):              {t_rrt_total:.2f}s')
    print(f'PRM* build + 3 queries:              {t_prm_total:.2f}s  '
          f'(build={t_build:.1f}s  queries={t_prm_queries:.2f}s)')
    avg_rrt_q_txt = t_rrt_total / max(n_rrt_ok, 1)
    avg_prm_q_txt = t_prm_queries / max(len([r for r in prm_results if r]), 1)
    if avg_rrt_q_txt > avg_prm_q_txt:
        be = t_build / (avg_rrt_q_txt - avg_prm_q_txt)
        print(f'Break-even: PRM* pays off after ≈ {be:.0f} queries')
    else:
        print(f'Note: PRM* query ({avg_prm_q_txt:.2f}s avg) is slower than RRT ({avg_rrt_q_txt:.2f}s avg) — '
              f'benefit is reliability / path quality, not raw speed')

    # ── Figure 1: trajectories ────────────────────────────────────────
    fig, axes = plt.subplots(1, 2, figsize=(14, 7))
    fig.suptitle('4×4 Maze — RRT vs PRM* trajectories', fontsize=13)

    for ax, title, results in zip(axes, ['RRT', f'PRM*  (roadmap {t_build:.0f}s)'], [rrt_results, prm_results]):
        ax.set_title(title)
        ax.set_aspect('equal')
        ax.set_xlim(MAZE_LIMITS[0])
        ax.set_ylim(MAZE_LIMITS[1])
        ax.grid(True, alpha=0.3)
        _draw_maze_obstacles(ax)
        for res, color in zip(results, MAZE_COLORS):
            if res is None:
                continue
            _plot_trajectory(ax, res['states'], res['start'], res['goal'],
                             color=color, label=res['name'])
        ax.legend(loc='upper right')

    plt.tight_layout()
    fig.savefig(f'{out_dir}/trajectories.png', dpi=150)
    print(f'Saved {out_dir}/trajectories.png')

    # ── Figure 2: timing breakdown ────────────────────────────────────
    fig2, (ax_abs, ax_amort) = plt.subplots(1, 2, figsize=(14, 5))
    fig2.suptitle('4×4 Maze — planning time comparison', fontsize=13)

    # Align by query name; NaN for failed queries
    all_names = [name for name, _, _ in MAZE_QUERIES]
    rrt_by_name = {r['name']: r for r in rrt_results if r}
    prm_by_name = {r['name']: r for r in prm_results if r}

    def _get(mapping, name, key):
        return mapping[name][key] if name in mapping else float('nan')

    rrt_ompl   = [_get(rrt_by_name, n, 't_ompl')   for n in all_names]
    rrt_bezier = [_get(rrt_by_name, n, 't_bezier') for n in all_names]
    prm_ompl   = [_get(prm_by_name, n, 't_ompl')   for n in all_names]
    prm_bezier = [_get(prm_by_name, n, 't_bezier') for n in all_names]

    x = np.arange(len(all_names))
    w = 0.35

    ax_abs.bar(x - w/2, rrt_ompl,   w, label='RRT — OMPL',    color='steelblue')
    ax_abs.bar(x - w/2, rrt_bezier, w, label='RRT — Bézier',  color='lightblue',  bottom=rrt_ompl)
    ax_abs.bar(x + w/2, prm_ompl,   w, label='PRM* — OMPL',   color='darkorange')
    ax_abs.bar(x + w/2, prm_bezier, w, label='PRM* — Bézier', color='moccasin',   bottom=prm_ompl)
    ax_abs.set_xticks(x); ax_abs.set_xticklabels(all_names)
    ax_abs.set_ylabel('seconds')
    ax_abs.set_title('Per-query planning time  (NaN bar = failed)')
    ax_abs.legend()
    ax_abs.grid(axis='y', alpha=0.3)

    # Amortised total: RRT × N vs build + N × query
    n_range = np.arange(1, 31)
    avg_rrt_q = np.nanmean([_get(rrt_by_name, n, 't_total') for n in all_names])
    avg_prm_q = np.nanmean([_get(prm_by_name, n, 't_total') for n in all_names])
    ax_amort.plot(n_range, avg_rrt_q * n_range,           'steelblue',   lw=2, label=f'RRT  (avg {avg_rrt_q:.2f}s/query)')
    ax_amort.plot(n_range, t_build + avg_prm_q * n_range, 'darkorange',  lw=2, label=f'PRM* build={t_build:.0f}s + avg {avg_prm_q:.2f}s/query')
    breakeven = t_build / (avg_rrt_q - avg_prm_q) if avg_rrt_q > avg_prm_q else None
    if breakeven is not None and 0 < breakeven < 100:
        ax_amort.axvline(breakeven, color='gray', ls='--', label=f'break-even ≈ {breakeven:.0f} queries')
    ax_amort.set_xlabel('number of agents / queries')
    ax_amort.set_ylabel('total seconds')
    ax_amort.set_title('Amortised cost vs number of queries')
    ax_amort.legend()
    ax_amort.grid(True, alpha=0.3)

    plt.tight_layout()
    fig2.savefig(f'{out_dir}/timing.png', dpi=150)
    print(f'Saved {out_dir}/timing.png')
    plt.close('all')


# ── Entry point  (switch MODE to select which test runs) ──────────────────────
MODE = 'benchmark'   # 'rrt'  |  'prm'  |  'benchmark'

if __name__ == '__main__':
    if MODE == 'benchmark':
        test_benchmark()
    elif MODE == 'prm':
        test_prm()
    else:
        test_rrt()
