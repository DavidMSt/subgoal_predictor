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
    from robot.control.motion_planning import plan_path, Waypoint, CircleObstacle, BoxObstacle, Bounds

    path = plan_path(
        start=(0.3, 0.3),
        end=(2.7, 2.7),
        waypoints=[Waypoint(1.5, 0.5, weight=0.8), Waypoint(1.5, 2.0, weight=0.2)],
        obstacles=[CircleObstacle(1.5, 1.2, 0.3)],
        bounds=Bounds(0, 3, 0, 3),
    )

    # Debug mode — returns PlanResult with all intermediate stages:
    result = plan_path(..., debug=True)
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
    """Uniformly sample spline (used for debug PlanResult)."""
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
                rrt_trees=rrt_trees_all,
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
