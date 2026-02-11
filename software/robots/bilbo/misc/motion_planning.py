"""
Motion Planner for BILBO robots.

Computes collision-free paths through a 2D workspace with:
- Weighted waypoints (weight controls proximity requirement)
- Circle and axis-aligned box obstacles
- Workspace boundaries
- Adaptive curvature-based output sampling

Algorithm pipeline:
    1. Segment-wise goal-biased RRT (straight line preferred when free)
    2. Greedy path pruning per segment
    3. Global waypoint zone optimization (minimize path length within zones)
    4. Re-planning between optimized waypoints
    5. Cubic spline smoothing with collision safety
    6. Adaptive curvature-based resampling

Usage:
    from robots.bilbo.misc.motion_planning import *

    path = plan_path(
        start=(0.3, 0.3),
        end=(2.7, 2.7),
        waypoints=[Waypoint(1.5, 0.5, weight=0.8), Waypoint(1.5, 2.0, weight=0.2)],
        obstacles=[CircleObstacle(1.5, 1.2, 0.3)],
        bounds=Bounds(0, 3, 0, 3),
    )

    # Debug mode — returns PlanResult with all intermediate stages:
    result = plan_path(..., debug=True)
    plot_stages(result)
"""

import dataclasses
import math
import random
from typing import Union

import numpy as np
from scipy.interpolate import CubicSpline

# ============================================================================
# Parameters
# ============================================================================

# Waypoint zone radii
WAYPOINT_RADIUS_MIN = 0.05   # [m] zone radius at weight=1 (must get close)
WAYPOINT_RADIUS_MAX = 3.0    # [m] zone radius at weight=0 (can pass far)

# RRT
RRT_STEP_SIZE = 0.10         # [m] max extension per iteration
RRT_MAX_ITERATIONS = 10000   # max iterations per segment
RRT_GOAL_BIAS = 0.10         # fraction of samples aimed at goal

# Safety
OBSTACLE_MARGIN = 0.05       # [m] clearance around obstacles

# Adaptive output sampling
SAMPLE_DS_MIN = 0.005        # [m] min sample spacing (tight curves)
SAMPLE_DS_MAX = 0.10         # [m] max sample spacing (straight segments)
SAMPLE_CURVATURE_GAIN = 2.0  # curvature sensitivity for step size

# Optimization
OPTIMIZATION_ITERATIONS = 5  # rounds of waypoint position relaxation

# ============================================================================
# Data Structures
# ============================================================================

@dataclasses.dataclass
class Waypoint:
    """Waypoint with proximity weight.
    weight=0 → large zone (WAYPOINT_RADIUS_MAX), path can pass far
    weight=1 → tight zone (WAYPOINT_RADIUS_MIN), path must pass close
    """
    x: float
    y: float
    weight: float = 0.5


@dataclasses.dataclass
class CircleObstacle:
    cx: float
    cy: float
    radius: float


@dataclasses.dataclass
class BoxObstacle:
    """Axis-aligned box defined by center and full dimensions."""
    cx: float
    cy: float
    width: float
    height: float


@dataclasses.dataclass
class Bounds:
    """Workspace limits. Treated as 4 wall obstacles internally."""
    x_min: float
    x_max: float
    y_min: float
    y_max: float


Obstacle = Union[CircleObstacle, BoxObstacle]


@dataclasses.dataclass
class PlanResult:
    """All intermediate stages from the planning pipeline (debug mode)."""
    path: list                  # final adaptively sampled path
    # Problem definition
    start: tuple
    end: tuple
    waypoints: list
    obstacles: list
    bounds: 'Bounds'
    # Phase 1: raw RRT / straight-line paths per segment
    rrt_trees: list             # [[(p1,p2), ...], ...] tree edges per segment
    rrt_paths: list             # [[(x,y), ...], ...]   solution path per segment
    # Phase 2: after pruning
    pruned_paths: list          # [[(x,y), ...], ...]   pruned path per segment
    # Connection points
    connection_points_before: list   # before optimization
    connection_points_after: list    # after optimization
    # Phase 3: merged polyline after re-planning
    polyline: list              # [(x,y), ...] full polyline before spline
    # Phase 4: spline curve (densely sampled for plotting)
    spline_curve: list          # [(x,y), ...] uniform dense samples


# ============================================================================
# Geometry & Collision Utilities
# ============================================================================

def _dist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _waypoint_zone_radius(weight: float) -> float:
    """Zone radius from weight. Higher weight → smaller radius."""
    w = max(0.0, min(1.0, weight))
    return WAYPOINT_RADIUS_MAX - w * (WAYPOINT_RADIUS_MAX - WAYPOINT_RADIUS_MIN)


def _seg_point_dist(p1, p2, cx, cy) -> float:
    """Minimum distance from line segment p1→p2 to point (cx, cy)."""
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    len_sq = dx * dx + dy * dy
    if len_sq < 1e-12:
        return math.hypot(cx - p1[0], cy - p1[1])
    t = max(0.0, min(1.0, ((cx - p1[0]) * dx + (cy - p1[1]) * dy) / len_sq))
    return math.hypot(cx - (p1[0] + t * dx), cy - (p1[1] + t * dy))


def _seg_intersects_aabb(p1, p2, xmin, ymin, xmax, ymax) -> bool:
    """Liang-Barsky line segment vs AABB intersection test."""
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    t0, t1 = 0.0, 1.0
    for origin, delta, lo, hi in [(p1[0], dx, xmin, xmax),
                                   (p1[1], dy, ymin, ymax)]:
        if abs(delta) < 1e-12:
            if origin < lo or origin > hi:
                return False
        else:
            ta = (lo - origin) / delta
            tb = (hi - origin) / delta
            if ta > tb:
                ta, tb = tb, ta
            t0 = max(t0, ta)
            t1 = min(t1, tb)
            if t0 > t1:
                return False
    return True


def _point_collides(px, py, obstacles: list[Obstacle],
                    margin: float = OBSTACLE_MARGIN) -> bool:
    for obs in obstacles:
        if isinstance(obs, CircleObstacle):
            if ((px - obs.cx) ** 2 + (py - obs.cy) ** 2
                    <= (obs.radius + margin) ** 2):
                return True
        elif isinstance(obs, BoxObstacle):
            if (abs(px - obs.cx) <= obs.width / 2 + margin
                    and abs(py - obs.cy) <= obs.height / 2 + margin):
                return True
    return False


def _line_collides(p1, p2, obstacles: list[Obstacle],
                   margin: float = OBSTACLE_MARGIN) -> bool:
    """Check if line segment p1→p2 intersects any obstacle (with margin)."""
    for obs in obstacles:
        if isinstance(obs, CircleObstacle):
            if _seg_point_dist(p1, p2, obs.cx, obs.cy) <= obs.radius + margin:
                return True
        elif isinstance(obs, BoxObstacle):
            hw = obs.width / 2 + margin
            hh = obs.height / 2 + margin
            if _seg_intersects_aabb(p1, p2,
                                    obs.cx - hw, obs.cy - hh,
                                    obs.cx + hw, obs.cy + hh):
                return True
    return False


def _bounds_to_walls(bounds: Bounds) -> list[BoxObstacle]:
    """Convert workspace bounds to 4 thick wall obstacles."""
    wt = 1.0  # wall thickness [m]
    w = bounds.x_max - bounds.x_min
    h = bounds.y_max - bounds.y_min
    mx = (bounds.x_min + bounds.x_max) / 2
    my = (bounds.y_min + bounds.y_max) / 2
    return [
        BoxObstacle(mx, bounds.y_min - wt / 2, w + 2 * wt, wt),  # bottom
        BoxObstacle(mx, bounds.y_max + wt / 2, w + 2 * wt, wt),  # top
        BoxObstacle(bounds.x_min - wt / 2, my, wt, h + 2 * wt),  # left
        BoxObstacle(bounds.x_max + wt / 2, my, wt, h + 2 * wt),  # right
    ]


# ============================================================================
# RRT Planner
# ============================================================================

class _RRTNode:
    __slots__ = ('x', 'y', 'parent')

    def __init__(self, x: float, y: float, parent=None):
        self.x = x
        self.y = y
        self.parent = parent


def _rrt_plan(start, goal_center, goal_radius, obstacles, bounds, rng,
              return_tree=False):
    """Goal-biased RRT. Returns path as list of (x,y), or None on failure.
    If return_tree=True, returns (path, tree_edges) where tree_edges is a
    list of ((x1,y1),(x2,y2)) for every edge added to the tree."""
    root = _RRTNode(start[0], start[1])
    nodes = [root]
    tree_edges = [] if return_tree else None

    for _ in range(RRT_MAX_ITERATIONS):
        # Biased sampling
        if rng.random() < RRT_GOAL_BIAS:
            sx, sy = goal_center
        else:
            sx = rng.uniform(bounds.x_min, bounds.x_max)
            sy = rng.uniform(bounds.y_min, bounds.y_max)

        # Nearest node (brute-force, fine for typical iteration counts)
        best = min(nodes, key=lambda n: (n.x - sx) ** 2 + (n.y - sy) ** 2)
        d = math.hypot(sx - best.x, sy - best.y)
        if d < 1e-9:
            continue

        # Steer toward sample
        step = min(RRT_STEP_SIZE, d)
        nx = best.x + (sx - best.x) / d * step
        ny = best.y + (sy - best.y) / d * step

        # Collision check
        if _line_collides((best.x, best.y), (nx, ny), obstacles):
            continue

        node = _RRTNode(nx, ny, parent=best)
        nodes.append(node)

        if return_tree:
            tree_edges.append(((best.x, best.y), (nx, ny)))

        # Goal reached?
        if (nx - goal_center[0]) ** 2 + (ny - goal_center[1]) ** 2 <= goal_radius ** 2:
            path = []
            n = node
            while n is not None:
                path.append((n.x, n.y))
                n = n.parent
            path = path[::-1]
            if return_tree:
                return path, tree_edges
            return path

    if return_tree:
        return None, tree_edges
    return None


# ============================================================================
# Path Pruning
# ============================================================================

def _prune_path(path, obstacles):
    """Greedy shortcutting: skip nodes when straight-line connection is free."""
    if len(path) <= 2:
        return list(path)

    result = [path[0]]
    i = 0
    while i < len(path) - 1:
        # Find the furthest node reachable from path[i] via straight line
        j = len(path) - 1
        while j > i + 1:
            if not _line_collides(path[i], path[j], obstacles):
                break
            j -= 1
        result.append(path[j])
        i = j

    return result


# ============================================================================
# Waypoint Zone Optimization
# ============================================================================

def _optimize_connection_points(points, zone_centers, zone_radii, obstacles):
    """
    Move connection points within their waypoint zones to minimize total
    path length. Start/end (radius=0) are kept fixed.

    For each movable point, finds the position in its zone disk that minimizes
    dist(prev, p) + dist(p, next) — the closest point on the prev→next line
    segment, clamped to the zone disk.
    """
    pts = list(points)

    for _ in range(OPTIMIZATION_ITERATIONS):
        changed = False
        for i in range(1, len(pts) - 1):
            r = zone_radii[i]
            if r <= 0:
                continue

            prev, nxt = pts[i - 1], pts[i + 1]
            center = zone_centers[i]

            # Project zone center onto line(prev, nxt), clamp to segment
            dx, dy = nxt[0] - prev[0], nxt[1] - prev[1]
            L2 = dx * dx + dy * dy
            if L2 < 1e-12:
                candidate = center
            else:
                t = ((center[0] - prev[0]) * dx + (center[1] - prev[1]) * dy) / L2
                t = max(0.0, min(1.0, t))
                proj = (prev[0] + t * dx, prev[1] + t * dy)
                d = _dist(proj, center)
                if d <= r:
                    # Line passes through zone — use projection directly
                    candidate = proj
                else:
                    # Closest point on zone boundary toward the line
                    candidate = (
                        center[0] + (proj[0] - center[0]) / d * r,
                        center[1] + (proj[1] - center[1]) / d * r,
                    )

            # Accept only if collision-free connections to neighbors
            if (not _point_collides(candidate[0], candidate[1], obstacles)
                    and not _line_collides(prev, candidate, obstacles)
                    and not _line_collides(candidate, nxt, obstacles)):
                if _dist(candidate, pts[i]) > 1e-6:
                    pts[i] = candidate
                    changed = True

        if not changed:
            break

    return pts


# ============================================================================
# Spline Fitting & Collision Safety
# ============================================================================

def _fit_parametric_spline(points):
    """Fit parametric cubic spline (arc-length parameterized).
    Returns (cs_x, cs_y, total_arc_length) or (None, None, 0)."""
    arr = np.array(points)
    seg_lengths = np.sqrt(np.sum(np.diff(arr, axis=0) ** 2, axis=1))
    t = np.concatenate([[0.0], np.cumsum(seg_lengths)])
    total = t[-1]
    if total < 1e-9:
        return None, None, 0.0

    cs_x = CubicSpline(t, arr[:, 0], bc_type='natural')
    cs_y = CubicSpline(t, arr[:, 1], bc_type='natural')
    return cs_x, cs_y, total


def _ensure_spline_safety(points, obstacles, max_rounds=5):
    """
    Fit spline, check for collisions along it, and subdivide problematic
    segments until collision-free (or max_rounds exceeded).
    Returns (cs_x, cs_y, total_length, final_control_points).
    """
    pts = list(points)

    for _ in range(max_rounds):
        cs_x, cs_y, L = _fit_parametric_spline(pts)
        if cs_x is None:
            return None, None, 0.0, pts

        # Dense collision check (~5mm resolution)
        n_check = max(int(L / 0.005), 100)
        ts = np.linspace(0, L, n_check)
        xs, ys = cs_x(ts), cs_y(ts)

        # Find first collision
        collision_t = None
        for k in range(n_check):
            if _point_collides(float(xs[k]), float(ys[k]), obstacles):
                collision_t = ts[k]
                break

        if collision_t is None:
            return cs_x, cs_y, L, pts  # all clear

        # Find which segment contains the collision and subdivide it
        arr = np.array(pts)
        seg_d = np.sqrt(np.sum(np.diff(arr, axis=0) ** 2, axis=1))
        seg_t = np.concatenate([[0.0], np.cumsum(seg_d)])
        seg_idx = int(np.searchsorted(seg_t, collision_t, side='right')) - 1
        seg_idx = max(0, min(seg_idx, len(pts) - 2))

        # Insert midpoint of the offending segment (midpoint on the straight
        # line between control points — this constrains the spline closer to
        # the collision-free polyline)
        mid = (
            (pts[seg_idx][0] + pts[seg_idx + 1][0]) / 2,
            (pts[seg_idx][1] + pts[seg_idx + 1][1]) / 2,
        )
        pts.insert(seg_idx + 1, mid)

    # Return best effort
    cs_x, cs_y, L = _fit_parametric_spline(pts)
    return cs_x, cs_y, L, pts


# ============================================================================
# Adaptive Curvature-Based Resampling
# ============================================================================

def _adaptive_resample(cs_x, cs_y, total_length,
                       ds_min=SAMPLE_DS_MIN, ds_max=SAMPLE_DS_MAX,
                       curvature_gain=SAMPLE_CURVATURE_GAIN):
    """
    Walk along spline with curvature-adaptive step size.
    Tight curves → dense samples, straights → sparse samples.

    Step size formula:
        ds = ds_min + (ds_max - ds_min) / (1 + curvature_gain * kappa)

    where kappa = |x'y'' - y'x''| / (x'^2 + y'^2)^(3/2) is the curvature.
    """
    if total_length < 1e-9:
        return [(float(cs_x(0.0)), float(cs_y(0.0)))]

    samples = []
    t = 0.0

    while t <= total_length:
        x = float(cs_x(t))
        y = float(cs_y(t))
        samples.append((x, y))

        # Curvature from parametric derivatives
        dx = float(cs_x(t, 1))
        dy = float(cs_y(t, 1))
        ddx = float(cs_x(t, 2))
        ddy = float(cs_y(t, 2))

        speed_sq = dx * dx + dy * dy
        speed = math.sqrt(speed_sq) if speed_sq > 1e-12 else 1.0
        if speed_sq > 1e-12:
            kappa = abs(dx * ddy - dy * ddx) / (speed_sq ** 1.5)
        else:
            kappa = 0.0

        # Target Euclidean step, then convert to parameter step via speed
        ds_euclidean = ds_min + (ds_max - ds_min) / (1.0 + curvature_gain * kappa)
        t += ds_euclidean / speed

    # Always include the exact endpoint
    end_pt = (float(cs_x(total_length)), float(cs_y(total_length)))
    if not samples or _dist(samples[-1], end_pt) > 1e-6:
        samples.append(end_pt)

    return samples


def _uniform_spline_samples(cs_x, cs_y, total_length, ds=0.005):
    """Uniformly sample spline for plotting."""
    n = max(int(total_length / ds), 2)
    ts = np.linspace(0, total_length, n)
    return [(float(cs_x(t)), float(cs_y(t))) for t in ts]


# ============================================================================
# Main Entry Point
# ============================================================================

def plan_path(
    start: tuple[float, float],
    end: tuple[float, float],
    waypoints: list[Waypoint] | None = None,
    obstacles: list[Obstacle] | None = None,
    bounds: Bounds | None = None,
    seed: int | None = None,
    debug: bool = False,
) -> 'list[tuple[float, float]] | PlanResult':
    """
    Plan a collision-free path from start to end through weighted waypoints.

    Parameters
    ----------
    start : (x, y)
        Start position (exact).
    end : (x, y)
        End position (exact).
    waypoints : list of Waypoint, optional
        Intermediate targets with proximity weights.
        weight=0: path can pass far (zone radius = WAYPOINT_RADIUS_MAX)
        weight=1: path must pass close (zone radius = WAYPOINT_RADIUS_MIN)
    obstacles : list of CircleObstacle / BoxObstacle, optional
    bounds : Bounds, optional
        Workspace limits (converted to wall obstacles).
        If None, inferred from points with padding.
    seed : int, optional
        RNG seed for reproducibility.
    debug : bool
        If True, return PlanResult with all intermediate pipeline stages
        instead of just the final path.

    Returns
    -------
    list of (x, y)  —  if debug=False (default)
        Adaptively sampled path — dense at curves, sparse on straights.
    PlanResult  —  if debug=True
        Contains .path plus all intermediate stages for visualization.
    """
    rng = random.Random(seed)
    waypoints = waypoints or []
    obstacles = list(obstacles) if obstacles else []

    # Infer bounds if not provided
    if bounds is None:
        all_x = [start[0], end[0]] + [wp.x for wp in waypoints]
        all_y = [start[1], end[1]] + [wp.y for wp in waypoints]
        pad = 2.0
        bounds = Bounds(min(all_x) - pad, max(all_x) + pad,
                        min(all_y) - pad, max(all_y) + pad)

    all_obstacles = obstacles + _bounds_to_walls(bounds)

    # Validate start/end
    if _point_collides(start[0], start[1], all_obstacles):
        raise ValueError(f"Start {start} is inside an obstacle or out of bounds")
    if _point_collides(end[0], end[1], all_obstacles):
        raise ValueError(f"End {end} is inside an obstacle or out of bounds")

    # Trivial case: start ≈ end
    if _dist(start, end) < 1e-6 and not waypoints:
        if debug:
            return PlanResult(
                path=[start], start=start, end=end, waypoints=waypoints,
                obstacles=obstacles, bounds=bounds, rrt_trees=[], rrt_paths=[],
                pruned_paths=[], connection_points_before=[start],
                connection_points_after=[start], polyline=[start],
                spline_curve=[start])
        return [start]

    # Build target sequence with zone info
    targets = [start] + [(wp.x, wp.y) for wp in waypoints] + [end]
    zone_radii = ([0.0]
                  + [_waypoint_zone_radius(wp.weight) for wp in waypoints]
                  + [0.0])
    zone_centers = list(targets)

    # ── Phase 1: Segment-wise RRT planning ──
    connection = start
    rrt_paths_all = []
    rrt_trees_all = []

    for i in range(len(targets) - 1):
        seg_start = connection
        seg_goal = targets[i + 1]
        goal_r = max(zone_radii[i + 1], RRT_STEP_SIZE)

        if not _line_collides(seg_start, seg_goal, all_obstacles):
            # Straight line is free
            raw_path = [seg_start, seg_goal]
            connection = seg_goal
            if debug:
                rrt_trees_all.append([])
        else:
            # Need RRT
            if debug:
                raw_path, tree = _rrt_plan(
                    seg_start, seg_goal, goal_r, all_obstacles, bounds, rng,
                    return_tree=True)
                rrt_trees_all.append(tree if tree else [])
            else:
                raw_path = _rrt_plan(
                    seg_start, seg_goal, goal_r, all_obstacles, bounds, rng)

            if raw_path is None:
                raise RuntimeError(
                    f"RRT failed for segment {i}: {seg_start} → {seg_goal}. "
                    f"Try increasing RRT_MAX_ITERATIONS or check obstacles.")

            # For exact targets (radius=0), extend to exact point if possible
            if zone_radii[i + 1] == 0.0 and _dist(raw_path[-1], seg_goal) > 1e-6:
                if not _line_collides(raw_path[-1], seg_goal, all_obstacles):
                    raw_path.append(seg_goal)
                    connection = seg_goal
                else:
                    connection = raw_path[-1]
            else:
                connection = raw_path[-1]

        rrt_paths_all.append(raw_path)

    # ── Phase 2: Prune each segment ──
    pruned_all = [_prune_path(seg, all_obstacles) for seg in rrt_paths_all]

    # Extract connection points from pruned segment endpoints
    conn_before = [pruned_all[0][0]]
    for seg in pruned_all:
        conn_before.append(seg[-1])
    conn_before[0] = start
    conn_before[-1] = end

    # ── Phase 3: Optimize connection points within waypoint zones ──
    conn_after = _optimize_connection_points(
        conn_before, zone_centers, zone_radii, all_obstacles
    )

    # ── Phase 4: Re-plan between optimized points ──
    full_path = []
    for i in range(len(conn_after) - 1):
        p1, p2 = conn_after[i], conn_after[i + 1]

        if _dist(p1, p2) < 1e-6:
            segment = [p1]
        elif not _line_collides(p1, p2, all_obstacles):
            segment = [p1, p2]
        else:
            raw = _rrt_plan(p1, p2, RRT_STEP_SIZE, all_obstacles, bounds, rng)
            if raw is None:
                raise RuntimeError(
                    f"Re-plan failed between optimized points {p1} → {p2}")
            segment = _prune_path(raw, all_obstacles)

        if i == 0:
            full_path.extend(segment)
        else:
            full_path.extend(segment[1:])  # skip duplicate junction point

    # Deduplicate consecutive near-identical points
    deduped = [full_path[0]]
    for p in full_path[1:]:
        if _dist(deduped[-1], p) > 1e-6:
            deduped.append(p)

    if len(deduped) < 2:
        deduped = [start, end]

    polyline = list(deduped)

    # ── Phase 5: Spline smoothing with collision safety ──
    cs_x, cs_y, L, final_pts = _ensure_spline_safety(deduped, all_obstacles)
    if cs_x is None:
        if debug:
            return PlanResult(
                path=deduped, start=start, end=end, waypoints=waypoints,
                obstacles=obstacles, bounds=bounds,
                rrt_trees=rrt_trees_all if debug else [],
                rrt_paths=rrt_paths_all, pruned_paths=pruned_all,
                connection_points_before=conn_before,
                connection_points_after=conn_after,
                polyline=polyline, spline_curve=deduped)
        return deduped

    # ── Phase 6: Adaptive curvature-based resampling ──
    final = _adaptive_resample(cs_x, cs_y, L)

    if debug:
        spline_curve = _uniform_spline_samples(cs_x, cs_y, L)
        return PlanResult(
            path=final, start=start, end=end, waypoints=waypoints,
            obstacles=obstacles, bounds=bounds,
            rrt_trees=rrt_trees_all, rrt_paths=rrt_paths_all,
            pruned_paths=pruned_all,
            connection_points_before=conn_before,
            connection_points_after=conn_after,
            polyline=polyline, spline_curve=spline_curve)

    return final


# ============================================================================
# Visualization — Single Path
# ============================================================================

def plot_path(path, start=None, end=None, waypoints=None, obstacles=None,
              bounds=None, title="Motion Plan", figsize=(8, 8)):
    """
    Visualize the planned path with obstacles, waypoint zones, and bounds.
    Returns (fig, ax) for further customization.
    """
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches

    fig, ax = plt.subplots(1, 1, figsize=figsize)
    ax.set_aspect('equal')
    ax.set_title(title)
    ax.grid(True, alpha=0.3)

    # Bounds
    if bounds:
        rect = patches.Rectangle(
            (bounds.x_min, bounds.y_min),
            bounds.x_max - bounds.x_min,
            bounds.y_max - bounds.y_min,
            linewidth=2, edgecolor='black', facecolor='none', linestyle='--',
        )
        ax.add_patch(rect)
        margin = 0.3
        ax.set_xlim(bounds.x_min - margin, bounds.x_max + margin)
        ax.set_ylim(bounds.y_min - margin, bounds.y_max + margin)

    # Obstacles
    if obstacles:
        for obs in obstacles:
            if isinstance(obs, CircleObstacle):
                c = patches.Circle(
                    (obs.cx, obs.cy), obs.radius,
                    facecolor='#ff6b6b', edgecolor='#c0392b',
                    alpha=0.6, linewidth=1.5,
                )
                ax.add_patch(c)
            elif isinstance(obs, BoxObstacle):
                r = patches.Rectangle(
                    (obs.cx - obs.width / 2, obs.cy - obs.height / 2),
                    obs.width, obs.height,
                    facecolor='#ff6b6b', edgecolor='#c0392b',
                    alpha=0.6, linewidth=1.5,
                )
                ax.add_patch(r)

    # Waypoint zones
    if waypoints:
        for wp in waypoints:
            r = _waypoint_zone_radius(wp.weight)
            zone = patches.Circle(
                (wp.x, wp.y), r,
                facecolor='#74b9ff', edgecolor='#0984e3',
                alpha=0.15, linewidth=1, linestyle='--',
            )
            ax.add_patch(zone)
            ax.plot(wp.x, wp.y, 'o', color='#0984e3', markersize=6, zorder=5)
            ax.annotate(
                f'w={wp.weight:.1f}\nr={r:.2f}m',
                (wp.x, wp.y),
                textcoords="offset points", xytext=(10, 8),
                fontsize=7, color='#0984e3',
            )

    # Path with sample points
    if path and len(path) >= 2:
        xs = [p[0] for p in path]
        ys = [p[1] for p in path]
        ax.plot(xs, ys, '-', color='#2d3436', linewidth=1.5,
                zorder=3, label='Path')
        ax.scatter(xs, ys, c='#636e72', s=3, zorder=4, label='Samples')

    # Start / End markers
    if start:
        ax.plot(start[0], start[1], 's', color='#00b894',
                markersize=10, zorder=6, label='Start')
    if end:
        ax.plot(end[0], end[1], '*', color='#d63031',
                markersize=14, zorder=6, label='End')

    ax.legend(loc='upper right', fontsize=8)
    ax.set_xlabel('x [m]')
    ax.set_ylabel('y [m]')
    plt.tight_layout()
    plt.show()
    return fig, ax


# ============================================================================
# Visualization — All Pipeline Stages
# ============================================================================

_SEGMENT_COLORS = [
    '#e17055', '#00b894', '#0984e3', '#6c5ce7', '#fdcb6e', '#e84393',
    '#00cec9', '#fab1a0', '#a29bfe', '#ffeaa7',
]


def _draw_background(ax, result: PlanResult, title, draw_zones=True):
    """Draw obstacles, bounds, waypoint zones, start/end on an axes."""
    import matplotlib.patches as patches

    ax.set_aspect('equal')
    ax.set_title(title, fontsize=10, fontweight='bold')
    ax.grid(True, alpha=0.2)

    b = result.bounds
    margin = 0.2
    ax.set_xlim(b.x_min - margin, b.x_max + margin)
    ax.set_ylim(b.y_min - margin, b.y_max + margin)

    # Bounds rectangle
    rect = patches.Rectangle(
        (b.x_min, b.y_min), b.x_max - b.x_min, b.y_max - b.y_min,
        linewidth=1.5, edgecolor='#2d3436', facecolor='none',
        linestyle='--', alpha=0.5)
    ax.add_patch(rect)

    # Obstacles
    for obs in result.obstacles:
        if isinstance(obs, CircleObstacle):
            p = patches.Circle(
                (obs.cx, obs.cy), obs.radius,
                facecolor='#ff6b6b', edgecolor='#c0392b',
                alpha=0.5, linewidth=1)
            ax.add_patch(p)
        elif isinstance(obs, BoxObstacle):
            p = patches.Rectangle(
                (obs.cx - obs.width / 2, obs.cy - obs.height / 2),
                obs.width, obs.height,
                facecolor='#ff6b6b', edgecolor='#c0392b',
                alpha=0.5, linewidth=1)
            ax.add_patch(p)

    # Waypoint zones
    if draw_zones:
        for idx, wp in enumerate(result.waypoints):
            r = _waypoint_zone_radius(wp.weight)
            zone = patches.Circle(
                (wp.x, wp.y), r,
                facecolor='#74b9ff', edgecolor='#0984e3',
                alpha=0.12, linewidth=0.8, linestyle='--')
            ax.add_patch(zone)
            ax.plot(wp.x, wp.y, 'o', color='#0984e3', markersize=4, zorder=5)
            ax.annotate(str(idx + 1), (wp.x, wp.y),
                        textcoords="offset points", xytext=(-3, -10),
                        fontsize=7, fontweight='bold', color='#0984e3',
                        ha='center', zorder=11)

    # Start / End
    ax.plot(result.start[0], result.start[1], 's', color='#00b894',
            markersize=8, zorder=10)
    ax.plot(result.end[0], result.end[1], '*', color='#d63031',
            markersize=10, zorder=10)


def plot_stages(result: PlanResult, figsize=(15, 13)):
    """
    4-panel plot showing all pipeline stages:
        1. Problem setup (input)
        2. RRT exploration + raw solution paths
        3. Pruned paths + optimized waypoints
        4. Final smoothed path with adaptive sampling

    Parameters
    ----------
    result : PlanResult from plan_path(..., debug=True)
    figsize : figure size

    Returns
    -------
    (fig, axes) — 2x2 array of axes
    """
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
    from matplotlib.collections import LineCollection

    fig, axes = plt.subplots(2, 2, figsize=figsize)

    # ── Panel 1: Problem Setup ──
    ax = axes[0, 0]
    _draw_background(ax, result, '1. Problem Setup')
    # Annotate waypoints with weight info
    for idx, wp in enumerate(result.waypoints):
        r = _waypoint_zone_radius(wp.weight)
        ax.annotate(
            f'WP{idx + 1}: w={wp.weight:.2f}, r={r:.2f}m',
            (wp.x, wp.y), textcoords="offset points", xytext=(8, 8),
            fontsize=7, color='#0984e3')
    ax.plot([], [], 's', color='#00b894', markersize=8, label='Start')
    ax.plot([], [], '*', color='#d63031', markersize=10, label='End')
    ax.plot([], [], 'o', color='#0984e3', markersize=5, label='Waypoint')
    ax.legend(loc='upper right', fontsize=7)

    # ── Panel 2: RRT Exploration ──
    ax = axes[0, 1]
    _draw_background(ax, result, '2. RRT Exploration')
    n_seg = len(result.rrt_paths)
    for seg_idx in range(n_seg):
        color = _SEGMENT_COLORS[seg_idx % len(_SEGMENT_COLORS)]

        # Tree edges as LineCollection (fast)
        if seg_idx < len(result.rrt_trees) and result.rrt_trees[seg_idx]:
            edges = result.rrt_trees[seg_idx]
            segments = [[(p1[0], p1[1]), (p2[0], p2[1])] for p1, p2 in edges]
            lc = LineCollection(segments, colors=color, alpha=0.06,
                                linewidths=0.4)
            ax.add_collection(lc)

        # Solution path through tree
        path = result.rrt_paths[seg_idx]
        if len(path) >= 2:
            xs = [p[0] for p in path]
            ys = [p[1] for p in path]
            ax.plot(xs, ys, '-', color=color, lw=2, alpha=0.85,
                    label=f'Seg {seg_idx + 1} ({len(path)} nodes)')
            ax.plot(xs[0], ys[0], 'o', color=color, markersize=4, zorder=6)
            ax.plot(xs[-1], ys[-1], 'D', color=color, markersize=4, zorder=6)

    ax.legend(loc='upper right', fontsize=6)

    # ── Panel 3: Pruned + Optimized ──
    ax = axes[1, 0]
    _draw_background(ax, result, '3. Pruned + Optimized')

    # Pruned segment paths (thin, colored)
    for seg_idx, seg_path in enumerate(result.pruned_paths):
        color = _SEGMENT_COLORS[seg_idx % len(_SEGMENT_COLORS)]
        xs = [p[0] for p in seg_path]
        ys = [p[1] for p in seg_path]
        ax.plot(xs, ys, 'o--', color=color, lw=1, markersize=3, alpha=0.5,
                label=f'Pruned {seg_idx + 1}' if seg_idx < 4 else None)

    # Connection points: before (hollow) → after (filled), with arrows
    cb = result.connection_points_before
    ca = result.connection_points_after
    for i in range(1, len(cb) - 1):
        bx, by = cb[i]
        ax_, ay_ = ca[i]
        # Before: hollow circle
        ax.plot(bx, by, 'o', color='#636e72', markersize=7,
                markerfacecolor='none', markeredgewidth=1.5, zorder=7)
        # After: filled circle
        ax.plot(ax_, ay_, 'o', color='#2d3436', markersize=5, zorder=8)
        # Arrow showing movement
        ddx, ddy = ax_ - bx, ay_ - by
        if math.hypot(ddx, ddy) > 0.01:
            ax.annotate(
                '', xy=(ax_, ay_), xytext=(bx, by),
                arrowprops=dict(arrowstyle='->', color='#636e72', lw=1.2),
                zorder=7)

    # Optimized polyline (bold)
    if len(result.polyline) >= 2:
        xs = [p[0] for p in result.polyline]
        ys = [p[1] for p in result.polyline]
        ax.plot(xs, ys, '.-', color='#2d3436', lw=2, markersize=5,
                zorder=5, label='Optimized polyline')

    # Legend entries for markers
    ax.plot([], [], 'o', color='#636e72', markerfacecolor='none',
            markeredgewidth=1.5, markersize=6, label='Before opt.')
    ax.plot([], [], 'o', color='#2d3436', markersize=5, label='After opt.')
    ax.legend(loc='upper right', fontsize=6)

    # ── Panel 4: Final Path with Adaptive Sampling ──
    ax = axes[1, 1]
    _draw_background(ax, result, '4. Final Path (adaptive sampling)')

    # Spline curve (thin reference line)
    if result.spline_curve and len(result.spline_curve) >= 2:
        xs = [p[0] for p in result.spline_curve]
        ys = [p[1] for p in result.spline_curve]
        ax.plot(xs, ys, '-', color='#b2bec3', lw=1, zorder=2, label='Spline')

    # Adaptive samples, colored by spacing
    if len(result.path) >= 2:
        xs = [p[0] for p in result.path]
        ys = [p[1] for p in result.path]
        spacings = [_dist(result.path[k], result.path[k + 1])
                     for k in range(len(result.path) - 1)]

        # Path line
        ax.plot(xs, ys, '-', color='#2d3436', lw=1.2, zorder=3)

        # Scatter colored by spacing (coolwarm_r: blue=dense, red=sparse)
        # Each point colored by spacing to the *next* point; last gets same
        # as second-to-last
        sp_colors = spacings + [spacings[-1]]
        sc = ax.scatter(xs, ys, c=sp_colors, cmap='coolwarm_r', s=8,
                        zorder=4, vmin=SAMPLE_DS_MIN, vmax=SAMPLE_DS_MAX,
                        edgecolors='none')
        cb = fig.colorbar(sc, ax=ax, shrink=0.6, pad=0.02)
        cb.set_label('Sample spacing [m]', fontsize=8)
        cb.ax.tick_params(labelsize=7)

        # Stats annotation
        total_len = sum(spacings)
        ax.text(
            0.02, 0.02,
            f'{len(result.path)} samples\n'
            f'Length: {total_len:.2f} m\n'
            f'Spacing: {min(spacings):.3f}–{max(spacings):.3f} m',
            transform=ax.transAxes, fontsize=7, verticalalignment='bottom',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))

    ax.legend(loc='upper right', fontsize=7)

    fig.suptitle('Motion Planning Pipeline', fontsize=13, fontweight='bold', y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.show()
    return fig, axes


# ============================================================================
# Demo
# ============================================================================

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


if __name__ == '__main__':
    b = Bounds(0, 3, 0, 3)

    # ── Example 1: No waypoints, wall with gap ──
    # Forces RRT to explore around a long horizontal wall.
    # Best for seeing the RRT tree structure.
    r1 = plan_path(
        start=(0.3, 0.5),
        end=(2.7, 2.5),
        obstacles=[
            BoxObstacle(1.2, 1.5, 2.0, 0.15),     # long horizontal wall
            CircleObstacle(2.5, 1.0, 0.25),         # guard bottom-right
            CircleObstacle(0.5, 2.2, 0.2),           # guard top-left
        ],
        bounds=b, seed=42, debug=True,
    )
    _print_result(r1, "Example 1: No waypoints — wall with gap")
    plot_stages(r1)

    # ── Example 2: Narrow corridor with waypoints ──
    # Two parallel walls create a corridor. Path must enter, visit a
    # tight waypoint inside, then exit to the far side.
    r2 = plan_path(
        start=(0.3, 1.5),
        end=(2.7, 1.5),
        waypoints=[
            Waypoint(1.5, 1.5, weight=0.95),  # inside corridor — very tight
            Waypoint(2.5, 0.5, weight=0.4),    # after corridor — loose
        ],
        obstacles=[
            BoxObstacle(1.5, 1.15, 1.8, 0.12),  # lower wall
            BoxObstacle(1.5, 1.85, 1.8, 0.12),  # upper wall
            CircleObstacle(2.3, 1.5, 0.15),      # obstacle after corridor exit
        ],
        bounds=b, seed=7, debug=True,
    )
    _print_result(r2, "Example 2: Narrow corridor with waypoints")
    plot_stages(r2)

    # ── Example 3: Scattered circles, zig-zag waypoints ──
    # Many circular obstacles force a winding path through the field.
    # Waypoints with mixed weights test the optimization.
    r3 = plan_path(
        start=(0.2, 0.2),
        end=(2.8, 2.8),
        waypoints=[
            Waypoint(0.5, 2.0, weight=0.8),   # top-left, tight
            Waypoint(1.5, 0.5, weight=0.3),    # bottom-center, loose
            Waypoint(2.5, 2.0, weight=0.6),    # right, moderate
        ],
        obstacles=[
            CircleObstacle(0.9, 1.2, 0.2),
            CircleObstacle(1.8, 1.8, 0.25),
            CircleObstacle(1.2, 2.3, 0.15),
            CircleObstacle(2.3, 1.0, 0.2),
            CircleObstacle(0.6, 0.7, 0.15),
            BoxObstacle(2.0, 2.6, 0.3, 0.25),
        ],
        bounds=b, seed=13, debug=True,
    )
    _print_result(r3, "Example 3: Scattered circles, zig-zag waypoints")
    plot_stages(r3)

    # ── Example 4: Dense box maze, single waypoint ──
    # Box obstacles form a partial maze. A single tight waypoint
    # forces the path through a specific part of the maze.
    r4 = plan_path(
        start=(0.2, 2.5),
        end=(2.8, 0.3),
        waypoints=[
            Waypoint(2.5, 2.5, weight=0.9),   # top-right corner, very tight
        ],
        obstacles=[
            BoxObstacle(1.0, 2.0, 0.15, 1.2),   # vertical wall left
            BoxObstacle(2.0, 1.0, 0.15, 1.2),   # vertical wall right
            BoxObstacle(1.5, 1.5, 0.8, 0.15),   # horizontal wall center
            CircleObstacle(0.5, 1.0, 0.2),
            CircleObstacle(2.5, 1.8, 0.15),
        ],
        bounds=b, seed=99, debug=True,
    )
    _print_result(r4, "Example 4: Dense box maze, single tight waypoint")
    plot_stages(r4)

    # ── Example 5: Waypoints only — weight showcase ──
    # No obstacles. Five waypoints placed off the diagonal from start to
    # end, each with a different weight. This isolates the effect of weight
    # on the path: high-weight waypoints pull the path close, low-weight
    # ones are almost ignored by the optimizer.
    r5 = plan_path(
        start=(0.2, 1.5),
        end=(2.8, 1.5),
        waypoints=[
            Waypoint(0.7, 2.5, weight=0.0),   # w=0 — huge zone, path won't detour
            Waypoint(1.1, 0.3, weight=0.25),   # w=0.25 — large zone, slight pull
            Waypoint(1.5, 2.7, weight=0.5),    # w=0.5 — medium zone
            Waypoint(1.9, 0.3, weight=0.75),   # w=0.75 — small zone, strong pull
            Waypoint(2.3, 2.7, weight=1.0),    # w=1.0 — tiny zone, must visit
        ],
        bounds=b, seed=0, debug=True,
    )
    _print_result(r5, "Example 5: Waypoints only — weight showcase (mixed)")
    for i, wp in enumerate(r5.waypoints):
        closest = min(_dist(p, (wp.x, wp.y)) for p in r5.path)
        zone_r = _waypoint_zone_radius(wp.weight)
        print(f"  WP{i + 1} ({wp.x}, {wp.y}) w={wp.weight:.2f}  "
              f"zone={zone_r:.2f}m  closest={closest:.4f}m")
    plot_stages(r5)

    # ── Example 6: Waypoints only — all tight, path follows them ──
    # Same zig-zag layout as example 5 but every waypoint has high weight
    # (0.9–1.0). The path must visit each one closely, producing a clear
    # zig-zag trajectory. Contrasts directly with example 5.
    r6 = plan_path(
        start=(0.2, 1.5),
        end=(2.8, 1.5),
        waypoints=[
            Waypoint(0.7, 2.5, weight=0.95),
            Waypoint(1.1, 0.3, weight=0.90),
            Waypoint(1.5, 2.7, weight=0.95),
            Waypoint(1.9, 0.3, weight=0.90),
            Waypoint(2.3, 2.7, weight=1.00),
        ],
        bounds=b, seed=0, debug=True,
    )
    _print_result(r6, "Example 6: Waypoints only — all tight weights")
    for i, wp in enumerate(r6.waypoints):
        closest = min(_dist(p, (wp.x, wp.y)) for p in r6.path)
        zone_r = _waypoint_zone_radius(wp.weight)
        print(f"  WP{i + 1} ({wp.x}, {wp.y}) w={wp.weight:.2f}  "
              f"zone={zone_r:.2f}m  closest={closest:.4f}m")
    plot_stages(r6)
