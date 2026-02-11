"""
Motion Planning Examples.

Run directly:
    python -m core.utils.control.lib_control.motion_planning.examples

Lists all available examples and lets you pick which one to run.
"""

import math

from core.utils.control.lib_control.motion_planning.motion_planning import (
    Bounds, BoxObstacle, CircleObstacle, PlanResult, StateConstraints, Waypoint,
    _dist, _draw_background, _waypoint_zone_radius, plan_path, plot_stages,
)

BOUNDS = Bounds(0, 3, 0, 3)


def _print_result(result: PlanResult, name: str):
    """Print summary statistics for a planning result."""
    print(f"\n{'─' * 50}")
    print(f"  {name}")
    print(f"{'─' * 50}")
    spacings = [_dist(result.path[i], result.path[i + 1])
                for i in range(len(result.path) - 1)]
    total_len = sum(spacings) if spacings else 0
    print(f"  Samples: {len(result.path)}")
    print(f"  Length:  {total_len:.3f} m")
    if spacings:
        print(f"  Spacing: {min(spacings):.4f}–{max(spacings):.4f} m "
              f"(mean {sum(spacings) / len(spacings):.4f})")
    for i, seg in enumerate(result.rrt_paths):
        tree_n = len(result.rrt_trees[i]) if i < len(result.rrt_trees) else 0
        pruned_n = len(result.pruned_paths[i])
        straight = " (straight)" if tree_n == 0 else ""
        print(f"  Seg {i + 1}: {len(seg)} RRT nodes, "
              f"{tree_n} tree edges, {pruned_n} pruned{straight}")


# ============================================================================
# Individual example functions
# ============================================================================

def example_1():
    """No waypoints, wall with gap"""
    r = plan_path(
        start=(0.3, 0.5),
        end=(2.7, 2.5),
        obstacles=[
            BoxObstacle(1.2, 1.5, 2.0, 0.15),
            CircleObstacle(2.5, 1.0, 0.25),
            CircleObstacle(0.5, 2.2, 0.2),
        ],
        bounds=BOUNDS, seed=42, debug=True,
    )
    _print_result(r, "Example 1: No waypoints — wall with gap")
    plot_stages(r)


def example_2():
    """Narrow corridor with waypoints"""
    r = plan_path(
        start=(0.3, 1.5),
        end=(2.7, 1.5),
        waypoints=[
            Waypoint(1.5, 1.5, weight=0.95),
            Waypoint(2.5, 0.5, weight=0.4),
        ],
        obstacles=[
            BoxObstacle(1.5, 1.15, 1.8, 0.12),
            BoxObstacle(1.5, 1.85, 1.8, 0.12),
            CircleObstacle(2.3, 1.5, 0.15),
        ],
        bounds=BOUNDS, seed=7, debug=True,
    )
    _print_result(r, "Example 2: Narrow corridor with waypoints")
    plot_stages(r)


def example_3():
    """Scattered circles, zig-zag waypoints"""
    r = plan_path(
        start=(0.2, 0.2),
        end=(2.8, 2.8),
        waypoints=[
            Waypoint(0.5, 2.0, weight=0.8),
            Waypoint(1.5, 0.5, weight=0.3),
            Waypoint(2.5, 2.0, weight=0.6),
        ],
        obstacles=[
            CircleObstacle(0.9, 1.2, 0.2),
            CircleObstacle(1.8, 1.8, 0.25),
            CircleObstacle(1.2, 2.3, 0.15),
            CircleObstacle(2.3, 1.0, 0.2),
            CircleObstacle(0.6, 0.7, 0.15),
            BoxObstacle(2.0, 2.6, 0.3, 0.25),
        ],
        bounds=BOUNDS, seed=13, debug=True,
    )
    _print_result(r, "Example 3: Scattered circles, zig-zag waypoints")
    plot_stages(r)


def example_4():
    """Dense box maze, single waypoint"""
    r = plan_path(
        start=(0.2, 2.5),
        end=(2.8, 0.3),
        waypoints=[
            Waypoint(2.5, 2.5, weight=0.9),
        ],
        obstacles=[
            BoxObstacle(1.0, 2.0, 0.15, 1.2),
            BoxObstacle(2.0, 1.0, 0.15, 1.2),
            BoxObstacle(1.5, 1.5, 0.8, 0.15),
            CircleObstacle(0.5, 1.0, 0.2),
            CircleObstacle(2.5, 1.8, 0.15),
        ],
        bounds=BOUNDS, seed=99, debug=True,
    )
    _print_result(r, "Example 4: Dense box maze, single tight waypoint")
    plot_stages(r)


def example_5():
    """Waypoints only — weight showcase (mixed)"""
    r = plan_path(
        start=(0.2, 1.5),
        end=(2.8, 1.5),
        waypoints=[
            Waypoint(0.7, 2.5, weight=0.0),
            Waypoint(1.1, 0.3, weight=0.25),
            Waypoint(1.5, 2.7, weight=0.5),
            Waypoint(1.9, 0.3, weight=0.75),
            Waypoint(2.3, 2.7, weight=1.0),
        ],
        bounds=BOUNDS, seed=0, debug=True,
    )
    _print_result(r, "Example 5: Waypoints only — weight showcase (mixed)")
    for i, wp in enumerate(r.waypoints):
        closest = min(_dist(p, (wp.x, wp.y)) for p in r.path)
        zone_r = _waypoint_zone_radius(wp.weight)
        print(f"  WP{i + 1} ({wp.x}, {wp.y}) w={wp.weight:.2f}  "
              f"zone={zone_r:.2f}m  closest={closest:.4f}m")
    plot_stages(r)


def example_6():
    """Waypoints only — all tight, path follows them"""
    r = plan_path(
        start=(0.2, 1.5),
        end=(2.8, 1.5),
        waypoints=[
            Waypoint(0.7, 2.5, weight=0.95),
            Waypoint(1.1, 0.3, weight=0.90),
            Waypoint(1.5, 2.7, weight=0.95),
            Waypoint(1.9, 0.3, weight=0.90),
            Waypoint(2.3, 2.7, weight=1.00),
        ],
        bounds=BOUNDS, seed=0, debug=True,
    )
    _print_result(r, "Example 6: Waypoints only — all tight weights")
    for i, wp in enumerate(r.waypoints):
        closest = min(_dist(p, (wp.x, wp.y)) for p in r.path)
        zone_r = _waypoint_zone_radius(wp.weight)
        print(f"  WP{i + 1} ({wp.x}, {wp.y}) w={wp.weight:.2f}  "
              f"zone={zone_r:.2f}m  closest={closest:.4f}m")
    plot_stages(r)


def example_7():
    """Rotated box obstacles (45 deg and 30 deg)"""
    r = plan_path(
        start=(0.3, 0.5),
        end=(2.7, 2.5),
        obstacles=[
            BoxObstacle(1.5, 1.5, 2.0, 0.15, psi=math.pi / 4),
            BoxObstacle(2.0, 0.8, 0.8, 0.15, psi=math.pi / 6),
            CircleObstacle(0.8, 2.0, 0.2),
        ],
        bounds=BOUNDS, seed=42, debug=True,
    )
    _print_result(r, "Example 7: Rotated box obstacles (45 deg and 30 deg)")
    plot_stages(r)


def example_8():
    """Rotated box chicane"""
    r = plan_path(
        start=(0.2, 1.5),
        end=(2.8, 1.5),
        waypoints=[
            Waypoint(1.5, 1.5, weight=0.7),
        ],
        obstacles=[
            BoxObstacle(0.8, 1.5, 1.2, 0.12, psi=math.pi / 3),
            BoxObstacle(1.5, 1.5, 1.2, 0.12, psi=-math.pi / 4),
            BoxObstacle(2.2, 1.5, 1.2, 0.12, psi=math.pi / 6),
        ],
        bounds=BOUNDS, seed=21, debug=True,
    )
    _print_result(r, "Example 8: Rotated box chicane")
    plot_stages(r)


def example_9():
    """Mixed rotated and axis-aligned obstacles"""
    r = plan_path(
        start=(0.3, 0.3),
        end=(2.7, 2.7),
        waypoints=[
            Waypoint(0.5, 2.5, weight=0.85),
            Waypoint(2.5, 0.5, weight=0.85),
        ],
        obstacles=[
            BoxObstacle(1.5, 1.5, 0.8, 0.15),
            BoxObstacle(1.5, 1.5, 0.15, 0.8),
            BoxObstacle(0.8, 2.0, 0.6, 0.12, psi=math.pi / 5),
            BoxObstacle(2.2, 1.0, 0.6, 0.12, psi=-math.pi / 5),
            CircleObstacle(1.5, 0.5, 0.15),
            CircleObstacle(1.5, 2.5, 0.15),
        ],
        bounds=BOUNDS, seed=55, debug=True,
    )
    _print_result(r, "Example 9: Mixed rotated and axis-aligned obstacles")
    plot_stages(r)


def example_10():
    """Padding = 0.15 m (robot half-width)"""
    r = plan_path(
        start=(0.3, 0.5),
        end=(2.7, 2.5),
        obstacles=[
            BoxObstacle(1.2, 1.5, 2.0, 0.15),
            CircleObstacle(2.5, 1.0, 0.25),
            CircleObstacle(0.5, 2.2, 0.2),
        ],
        bounds=BOUNDS, seed=42, padding=0.15, debug=True,
    )
    _print_result(r, "Example 10: Padding = 0.15 m (robot half-width)")
    plot_stages(r)


def example_11():
    """Smoothing comparison (0.0, 0.5, 1.0 side by side)"""
    import matplotlib.pyplot as plt

    obstacles = [
        BoxObstacle(1.2, 1.5, 2.0, 0.15),
        CircleObstacle(2.5, 1.0, 0.25),
        CircleObstacle(0.5, 2.2, 0.2),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    for ax, s in zip(axes, [0.0, 0.75, 1.0]):
        result = plan_path(
            start=(0.3, 0.5), end=(2.7, 2.5),
            obstacles=obstacles,
            bounds=BOUNDS, seed=42, smoothing=s, debug=True,
        )
        spacings = [_dist(result.path[k], result.path[k + 1])
                     for k in range(len(result.path) - 1)]
        total_len = sum(spacings) if spacings else 0
        _print_result(result, f"Example 11: smoothing={s}")

        _draw_background(ax, result, f'smoothing = {s}')

        if len(result.polyline) >= 2:
            xs = [p[0] for p in result.polyline]
            ys = [p[1] for p in result.polyline]
            ax.plot(xs, ys, '--', color='#b2bec3', lw=1, zorder=2, label='Polyline')

        xs = [p[0] for p in result.path]
        ys = [p[1] for p in result.path]
        ax.plot(xs, ys, '-', color='#2d3436', lw=1.5, zorder=3, label='Final path')
        ax.scatter(xs, ys, c='#636e72', s=4, zorder=4)

        ax.text(
            0.02, 0.02,
            f'{len(result.path)} samples\nLength: {total_len:.2f} m',
            transform=ax.transAxes, fontsize=8, verticalalignment='bottom',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))
        ax.legend(loc='upper right', fontsize=7)

    fig.suptitle('Smoothing Comparison', fontsize=13, fontweight='bold')
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.show()


def example_12():
    """Padding + rotated obstacles"""
    r = plan_path(
        start=(0.3, 0.5),
        end=(2.7, 2.5),
        obstacles=[
            BoxObstacle(1.5, 1.5, 2.0, 0.15, psi=math.pi / 4),
            BoxObstacle(2.0, 0.8, 0.8, 0.15, psi=math.pi / 6),
            CircleObstacle(0.8, 2.0, 0.2),
        ],
        bounds=BOUNDS, seed=42, padding=0.12, debug=True,
    )
    _print_result(r, "Example 12: Padding + rotated obstacles")
    plot_stages(r)


def example_13():
    """State constraints — restricted x/y corridor"""
    r = plan_path(
        start=(0.5, 0.5),
        end=(2.0, 2.5),
        waypoints=[
            Waypoint(1.0, 2.0, weight=0.99),
            Waypoint(1.5, 1.0, weight=0.99),
            Waypoint(2.0, 1.5, weight=0.99),
        ],
        obstacles=[
            CircleObstacle(1.5, 1.5, 0.3),
            CircleObstacle(0.8, 1.0, 0.15),
        ],
        bounds=BOUNDS,
        state_constraints=StateConstraints(x_min=0.3, x_max=2.2, y_min=0.3),
        seed=42, debug=True,
        padding=0.05
    )
    _print_result(r, "Example 13: State constraints — restricted corridor")
    plot_stages(r)


# ============================================================================
# Registry and interactive runner
# ============================================================================

EXAMPLES = [
    (1,  "No waypoints — wall with gap",              example_1),
    (2,  "Narrow corridor with waypoints",             example_2),
    (3,  "Scattered circles, zig-zag waypoints",       example_3),
    (4,  "Dense box maze, single tight waypoint",      example_4),
    (5,  "Waypoints only — weight showcase (mixed)",   example_5),
    (6,  "Waypoints only — all tight weights",         example_6),
    (7,  "Rotated box obstacles (45 deg and 30 deg)",  example_7),
    (8,  "Rotated box chicane",                        example_8),
    (9,  "Mixed rotated and axis-aligned obstacles",   example_9),
    (10, "Padding = 0.15 m (robot half-width)",        example_10),
    (11, "Smoothing comparison (side by side)",         example_11),
    (12, "Padding + rotated obstacles",                example_12),
    (13, "State constraints — restricted corridor",    example_13),
]


def run_examples():
    """Interactive example picker. Lists examples and lets the user choose."""
    while True:
        print(f"\n{'=' * 55}")
        print("  Motion Planning Examples")
        print(f"{'=' * 55}")
        for num, desc, _ in EXAMPLES:
            print(f"  {num:>2}.  {desc}")
        print(f"   a.  Run all")
        print(f"   q.  Quit")
        print(f"{'─' * 55}")

        choice = input("  Select example: ").strip().lower()

        if choice == 'q':
            break

        if choice == 'a':
            for num, _, func in EXAMPLES:
                func()
            continue

        try:
            num = int(choice)
        except ValueError:
            print(f"  Invalid input: '{choice}'")
            continue

        match = [func for n, _, func in EXAMPLES if n == num]
        if not match:
            print(f"  No example {num}. Choose 1–{EXAMPLES[-1][0]}.")
            continue

        match[0]()


if __name__ == '__main__':
    run_examples()
