#!/usr/bin/env python3
"""Debug script: test the motion planner output directly (no firmware needed).

Tests uniform path resampling and simulates firmware-side curvature estimation.
"""

import math
import sys
import os

# Ensure imports work from the robot software tree
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.utils.control.lib_control.motion_planning.common import (
    _uniform_resample, _adaptive_resample, Waypoint, Bounds,
    _fit_parametric_spline, _ensure_spline_safety, UNIFORM_DS,
)
from core.utils.control.lib_control.motion_planning.rrt import plan_path

import numpy as np


def menger_curvature(ax, ay, bx, by, cx, cy):
    """Menger curvature of triangle ABC (same as firmware)."""
    abx, aby = bx - ax, by - ay
    acx, acy = cx - ax, cy - ay
    bcx, bcy = cx - bx, cy - by
    cross = abs(abx * acy - aby * acx)
    ab = math.sqrt(abx**2 + aby**2)
    bc = math.sqrt(bcx**2 + bcy**2)
    ac = math.sqrt(acx**2 + acy**2)
    denom = ab * bc * ac
    if denom < 1e-10:
        return 0.0
    return 2.0 * cross / denom


def estimate_curvature_ahead(points, idx, lookahead_dist, cumul_dist):
    """Python simulation of firmware _estimate_curvature_ahead()."""
    n = len(points)
    if n < 3:
        return 0.0

    start_idx = min(idx, n - 2)
    start_arc = cumul_dist[start_idx]
    end_arc = start_arc + lookahead_dist

    end_idx = start_idx
    while end_idx < n - 1 and cumul_dist[end_idx] < end_arc:
        end_idx += 1

    # Compute stride: ~50mm chord
    total_length = cumul_dist[-1]
    avg_spacing = total_length / max(n - 1, 1)
    stride = max(1, min(15, int(0.05 / max(avg_spacing, 0.001))))

    if end_idx < start_idx + 2 * stride:
        if start_idx + 2 * stride < n:
            end_idx = start_idx + 2 * stride
        else:
            return 0.0

    max_kappa = 0.0
    i = start_idx
    while i + 2 * stride <= end_idx and i + 2 * stride < n:
        kappa = menger_curvature(
            points[i][0], points[i][1],
            points[i + stride][0], points[i + stride][1],
            points[i + 2 * stride][0], points[i + 2 * stride][1],
        )
        max_kappa = max(max_kappa, kappa)
        i += 1

    return max_kappa


def analyze_path(points, label, max_speed=0.6, curvature_gain=2.0, curvature_lookahead=0.3):
    """Analyze a planned path: spacing distribution and firmware curvature-based speeds."""
    if not points or len(points) < 2:
        print(f"  [{label}] No points or < 2 points!")
        return

    spacings = []
    for i in range(len(points) - 1):
        dx = points[i+1][0] - points[i][0]
        dy = points[i+1][1] - points[i][1]
        spacings.append(math.sqrt(dx*dx + dy*dy))

    spacings = np.array(spacings)

    # Compute cumulative distances (same as firmware)
    cumul_dist = np.zeros(len(points))
    for i in range(1, len(points)):
        cumul_dist[i] = cumul_dist[i-1] + spacings[i-1]

    # Simulate firmware curvature-based speed at each segment
    fw_speeds = np.zeros(len(spacings))
    for i in range(len(spacings)):
        kappa = estimate_curvature_ahead(points, i, curvature_lookahead, cumul_dist)
        fw_speeds[i] = max_speed / (1.0 + curvature_gain * kappa)

    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  Points:        {len(points)}")
    print(f"  Total length:  {spacings.sum():.3f} m")
    print(f"  Max spacing:   {spacings.max()*1000:.1f} mm")
    print(f"  Min spacing:   {spacings.min()*1000:.2f} mm")
    print(f"  Mean spacing:  {spacings.mean()*1000:.1f} mm")
    print(f"  Std spacing:   {spacings.std()*1000:.2f} mm")
    print(f"  Curvature-based speed range: {fw_speeds.min():.3f} - {fw_speeds.max():.3f} m/s")
    print()

    # Show spacing histogram
    bins = [0, 5.0, 10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 50.0, 100.0, 200.0]
    print(f"  Spacing histogram (mm):")
    for i in range(len(bins)-1):
        count = np.sum((spacings*1000 >= bins[i]) & (spacings*1000 < bins[i+1]))
        if count > 0:
            bar = '#' * min(count, 40)
            print(f"    {bins[i]:5.1f}-{bins[i+1]:5.1f}: {count:4d} {bar}")
    count_large = np.sum(spacings*1000 >= bins[-1])
    if count_large > 0:
        print(f"    >{bins[-1]:5.1f}: {count_large:4d}")

    # Show segments with curvature-based speed at key sections
    print(f"\n  First 10 segments:")
    for i in range(min(10, len(spacings))):
        kappa = estimate_curvature_ahead(points, i, curvature_lookahead, cumul_dist)
        print(f"    [{i:3d}] spacing={spacings[i]*1000:6.2f}mm  κ={kappa:.2f}  v={fw_speeds[i]:.3f} m/s  pos=({points[i][0]:.3f}, {points[i][1]:.3f})")

    # Find segment with highest curvature
    all_kappas = [estimate_curvature_ahead(points, i, curvature_lookahead, cumul_dist) for i in range(len(spacings))]
    peak_idx = int(np.argmax(all_kappas))
    print(f"\n  Peak curvature region (around idx {peak_idx}):")
    for i in range(max(0, peak_idx-3), min(len(spacings), peak_idx+4)):
        kappa = all_kappas[i]
        print(f"    [{i:3d}] spacing={spacings[i]*1000:6.2f}mm  κ={kappa:.2f}  v={fw_speeds[i]:.3f} m/s  pos=({points[i][0]:.3f}, {points[i][1]:.3f})")

    print(f"\n  Last 10 segments:")
    for i in range(max(0, len(spacings)-10), len(spacings)):
        kappa = all_kappas[i]
        print(f"    [{i:3d}] spacing={spacings[i]*1000:6.2f}mm  κ={kappa:.2f}  v={fw_speeds[i]:.3f} m/s  pos=({points[i][0]:.3f}, {points[i][1]:.3f})")


def test_straight_line():
    """Straight line — should have uniform spacing and max speed everywhere."""
    print("\n" + "="*60)
    print("TEST 1: Straight line (0,0) -> (2,0)")
    print("="*60)

    path = plan_path(
        start=(0.0, 0.0), end=(2.0, 0.0),
    )
    analyze_path(path, "Straight line")


def test_90_degree_turn():
    """L-shaped path with a 90-degree corner via waypoint."""
    print("\n" + "="*60)
    print("TEST 2: 90-degree turn via waypoint at (1, 0)")
    print("="*60)

    path = plan_path(
        start=(0.0, 0.0), end=(1.0, 1.0),
        waypoints=[Waypoint(1.0, 0.0, weight=1.0)],
        smoothing=0.85,
    )
    analyze_path(path, "90-deg turn (smoothing=0.85)")


def test_stop_waypoint():
    """Path with a STOP waypoint — verify it's an exact path point."""
    print("\n" + "="*60)
    print("TEST 3: Path with STOP waypoint at (1, 0)")
    print("="*60)

    stop_x, stop_y = 1.0, 0.0
    path = plan_path(
        start=(0.0, 0.0), end=(2.0, 0.0),
        waypoints=[Waypoint(stop_x, stop_y, weight=1.0, stop=True)],
    )

    # Find closest point to STOP position
    best_dist = float('inf')
    best_idx = 0
    for i, (x, y) in enumerate(path):
        d = math.sqrt((x - stop_x)**2 + (y - stop_y)**2)
        if d < best_dist:
            best_dist = d
            best_idx = i

    print(f"  STOP waypoint ({stop_x}, {stop_y})")
    print(f"  Closest path point: idx={best_idx}, dist={best_dist*1000:.2f}mm")
    print(f"    pos=({path[best_idx][0]:.4f}, {path[best_idx][1]:.4f})")

    analyze_path(path, "With STOP at (1,0)")


def test_curvature_sensitivity():
    """Test different curvature_gain values to see speed range in corners."""
    print("\n" + "="*60)
    print("TEST 4: Curvature gain sensitivity on 90-deg corner")
    print("="*60)

    path = plan_path(
        start=(0.0, 0.0), end=(1.0, 1.0),
        waypoints=[Waypoint(1.0, 0.0, weight=1.0)],
        smoothing=0.85,
    )

    for gain in [1.0, 2.0, 4.0, 8.0]:
        # Compute speed range
        spacings = []
        for i in range(len(path) - 1):
            dx = path[i+1][0] - path[i][0]
            dy = path[i+1][1] - path[i][1]
            spacings.append(math.sqrt(dx*dx + dy*dy))
        cumul_dist = np.zeros(len(path))
        for i in range(1, len(path)):
            cumul_dist[i] = cumul_dist[i-1] + spacings[i-1]

        speeds = []
        for i in range(len(spacings)):
            kappa = estimate_curvature_ahead(path, i, 0.3, cumul_dist)
            speeds.append(0.6 / (1.0 + gain * kappa))
        speeds = np.array(speeds)
        print(f"  curvature_gain={gain:.1f}: speed {speeds.min():.3f} - {speeds.max():.3f} m/s "
              f"(min at idx {np.argmin(speeds)}, κ_max={max(estimate_curvature_ahead(path, i, 0.3, cumul_dist) for i in range(len(spacings))):.2f})")


def test_uniform_resampler():
    """Verify _uniform_resample is being called."""
    print("\n" + "="*60)
    print("TEST 5: Verify _uniform_resample is used")
    print("="*60)

    import core.utils.control.lib_control.motion_planning.common as mp_common

    original_uniform = mp_common._uniform_resample
    called = {'uniform': False}

    def patched_uniform(*args, **kwargs):
        called['uniform'] = True
        print("  >>> _uniform_resample CALLED")
        return original_uniform(*args, **kwargs)

    mp_common._uniform_resample = patched_uniform

    plan_path(
        start=(0.0, 0.0), end=(1.0, 0.0),
    )

    mp_common._uniform_resample = original_uniform
    print(f"\n  Results: uniform_resample={called['uniform']}")


if __name__ == '__main__':
    test_uniform_resampler()
    test_straight_line()
    test_90_degree_turn()
    test_stop_waypoint()
    test_curvature_sensitivity()
