"""Grid search for MPPI parameters in the 4x4 maze scenario.

Lean version: K=200, max 500 steps, smaller grid, 1 seed.
"""

import itertools
import logging
import numpy as np
import time
import sys

from master_thesis.universal.universal_simulation import FRODO_Universal_Simulation
from master_thesis.universal.reactive_agent import FRODOReactiveAgent
from pathlib import Path
from master_thesis.scenarios.testbed_importer import load_scenario_yaml

_MAZE_4X4_YAML = Path(__file__).parent.parent / 'master_thesis' / 'scenarios' / 'maze_4x4.yaml'
from master_thesis.modules.local_control.mppi_controller import MPPIConfig
from master_thesis.modules.task_assignment.strategies.strategy_registry import StrategyType

# Suppress all sim logging
logging.disable(logging.CRITICAL)


def run_trial(
    horizon: int,
    n_samples: int,
    heading_weight: float,
    noise_psi_dot: float,
    temperature: float,
    obstacle_weight: float,
    max_steps: int = 500,
    goal_threshold: float = 0.2,
    seed: int = 42,
) -> dict:
    """Run one agent in the 4x4 maze and return metrics."""
    np.random.seed(seed)

    sim = FRODO_Universal_Simulation(Ts=0.1, limits=((-2, 2), (-2, 2)), run_mode='fast')
    sim.init()

    # Load maze obstacles
    cfg = load_scenario_yaml(_MAZE_4X4_YAML.read_text())
    for obs in cfg.obstacles:
        sim.new_obstacle(obs.obstacle_id, x=obs.x, y=obs.y, psi=obs.psi,
                         length=obs.length, width=obs.width, height=obs.height)

    # Single agent: bottom-left corner → top-right goal (requires navigating the full maze)
    agent = sim.new_agent(
        'test_agent',
        agent_class=FRODOReactiveAgent,
        start_config=(-1.75, -1.75, 0.0),
        log_level='ERROR',
        mppi_horizon=horizon,
        mppi_n_samples=n_samples,
    )

    # Patch the MPPI config
    from master_thesis.modules.execution.reactive_executor import ReactiveExecutor
    assert isinstance(agent.executor, ReactiveExecutor)
    mppi = agent.executor._lcm.controller
    mppi.config.heading_weight = heading_weight
    mppi.config.noise_sigma = np.array([0.3, noise_psi_dot])
    mppi.config.temperature = temperature
    mppi.config.obstacle_weight = obstacle_weight

    sim.new_task('test_goal', x=1.75, y=1.75, psi=0.0)

    # Centralized TA (instant)
    sim.start_ta(strategy=StrategyType.HUNGARIAN)
    sim.start_mp()
    sim.start_exe()

    # Step simulation
    t0 = time.perf_counter()
    reached = False
    min_dist = float('inf')
    progress_x = []  # track x position to detect stuck

    for step_i in range(max_steps):
        sim.step()

        ax, ay = agent.container.x, agent.container.y
        dist = np.hypot(ax - 1.75, ay - 1.75)
        min_dist = min(min_dist, dist)

        if step_i % 50 == 0:
            progress_x.append(ax)

        if dist < goal_threshold:
            reached = True
            break

        # Early termination: if after 200 steps the agent hasn't moved 0.3m, it's stuck
        if step_i == 200 and len(progress_x) >= 2:
            total_move = np.hypot(ax - (-1.75), ay - (-1.75))
            if total_move < 0.3:
                break

    elapsed = time.perf_counter() - t0
    final_dist = np.hypot(agent.container.x - 1.75, agent.container.y - 1.75)
    steps_taken = step_i + 1

    return {
        'reached': reached,
        'steps': steps_taken,
        'time_sim': steps_taken * 0.1,
        'time_wall': elapsed,
        'final_dist': final_dist,
        'min_dist': min_dist,
    }


def main():
    # Smaller, focused grid
    horizons = [8, 12, 15, 20]
    heading_weights = [5.0, 10.0, 20.0]
    noise_psi_dots = [0.8, 1.2, 1.8]
    temperatures = [0.5, 1.0]
    obstacle_weights = [80.0]  # fix this for now

    n_samples = 200  # much faster than 1000

    combos = list(itertools.product(horizons, heading_weights, noise_psi_dots, temperatures, obstacle_weights))
    print(f"Testing {len(combos)} configs (K={n_samples})")
    print(f"{'#':>4} {'H':>3} {'hw':>5} {'ns':>4} {'T':>4} | {'reach':>5} {'steps':>6} {'fin_d':>6} {'min_d':>6} {'wall':>5}")
    print("-" * 65)

    results = []

    for i, (h, hw, ns, temp, ow) in enumerate(combos):
        r = run_trial(
            horizon=h, n_samples=n_samples,
            heading_weight=hw, noise_psi_dot=ns,
            temperature=temp, obstacle_weight=ow,
        )

        results.append({
            'h': h, 'hw': hw, 'ns': ns, 'temp': temp,
            'reached': r['reached'], 'steps': r['steps'],
            'final_dist': r['final_dist'], 'min_dist': r['min_dist'],
            'wall': r['time_wall'],
        })

        flag = "OK" if r['reached'] else "  "
        print(f"{i+1:4d} {h:3d} {hw:5.1f} {ns:4.1f} {temp:4.1f} | {flag:>5} {r['steps']:6d} {r['final_dist']:6.2f} {r['min_dist']:6.3f} {r['time_wall']:5.1f}")
        sys.stdout.flush()

    # Sort and print top results
    print("\n" + "=" * 65)
    print("TOP 10 (sorted by: reached > fewer steps > closer min_dist)")
    print("=" * 65)
    results.sort(key=lambda r: (-int(r['reached']), r['steps'], r['min_dist']))
    for r in results[:10]:
        flag = "OK" if r['reached'] else "--"
        print(f"  {flag}  H={r['h']:2d}  hw={r['hw']:5.1f}  ns={r['ns']:3.1f}  T={r['temp']:3.1f}"
              f"  | steps={r['steps']:5d}  fin_d={r['final_dist']:.2f}  min_d={r['min_dist']:.3f}  wall={r['wall']:.1f}s")

    n_reached = sum(1 for r in results if r['reached'])
    print(f"\n{n_reached} / {len(results)} configs reached the goal")


if __name__ == '__main__':
    main()
