"""
Motion Planner for BILBO robots.

Computes collision-free paths through a 2D workspace with:
- Weighted waypoints (weight controls proximity requirement)
- Circle and box obstacles (boxes support rotation via psi angle)
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
    from core.utils.control.lib_control.motion_planning import *

    path = plan_path(
        start=(0.3, 0.3),
        end=(2.7, 2.7),
        waypoints=[Waypoint(1.5, 0.5, weight=0.8), Waypoint(1.5, 2.0, weight=0.2)],
        obstacles=[CircleObstacle(1.5, 1.2, 0.3)],
        bounds=Bounds(0, 3, 0, 3),
    )

    # Rotated box obstacle (45 degree rotation around center):
    path = plan_path(
        start=(0.3, 0.3),
        end=(2.7, 2.7),
        obstacles=[BoxObstacle(1.5, 1.5, 1.0, 0.2, psi=math.pi/4)],
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
    """Box defined by center, full dimensions, and rotation angle.

    Parameters
    ----------
    cx, cy : float
        Center of the box.
    width : float
        Full extent along the box's local x-axis.
    height : float
        Full extent along the box's local y-axis.
    psi : float
        Rotation angle in radians around the center (counterclockwise).
        Default 0.0 gives an axis-aligned box.
    """
    cx: float
    cy: float
    width: float
    height: float
    psi: float = 0.0


@dataclasses.dataclass
class Bounds:
    """Workspace limits. Treated as 4 wall obstacles internally."""
    x_min: float
    x_max: float
    y_min: float
    y_max: float


@dataclasses.dataclass
class StateConstraints:
    """Optional per-axis position constraints.
    Only specified limits (non-None) are enforced as wall obstacles."""
    x_min: float | None = None
    x_max: float | None = None
    y_min: float | None = None
    y_max: float | None = None


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
    padding: float              # robot padding used for planning
    state_constraints: 'StateConstraints | None'  # per-axis position constraints
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


def _rotate_to_local(px, py, cx, cy, cos_psi, sin_psi):
    """Transform point (px, py) into the local frame of a box at (cx, cy)
    rotated by psi. cos_psi and sin_psi are precomputed."""
    dx = px - cx
    dy = py - cy
    # Inverse rotation (rotate by -psi)
    lx = cos_psi * dx + sin_psi * dy
    ly = -sin_psi * dx + cos_psi * dy
    return lx, ly


def _point_collides(px, py, obstacles: list[Obstacle],
                    margin: float = OBSTACLE_MARGIN) -> bool:
    for obs in obstacles:
        if isinstance(obs, CircleObstacle):
            if ((px - obs.cx) ** 2 + (py - obs.cy) ** 2
                    <= (obs.radius + margin) ** 2):
                return True
        elif isinstance(obs, BoxObstacle):
            cos_psi = math.cos(obs.psi)
            sin_psi = math.sin(obs.psi)
            lx, ly = _rotate_to_local(px, py, obs.cx, obs.cy, cos_psi, sin_psi)
            if (abs(lx) <= obs.width / 2 + margin
                    and abs(ly) <= obs.height / 2 + margin):
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
            # Transform segment endpoints into the box's local frame
            cos_psi = math.cos(obs.psi)
            sin_psi = math.sin(obs.psi)
            lp1 = _rotate_to_local(p1[0], p1[1], obs.cx, obs.cy, cos_psi, sin_psi)
            lp2 = _rotate_to_local(p2[0], p2[1], obs.cx, obs.cy, cos_psi, sin_psi)
            if _seg_intersects_aabb(lp1, lp2, -hw, -hh, hw, hh):
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


def _state_constraints_to_walls(constraints: StateConstraints,
                                bounds: Bounds) -> list[BoxObstacle]:
    """Convert per-axis state constraints to wall obstacles."""
    walls = []
    wt = 1.0  # wall thickness
    w = bounds.x_max - bounds.x_min
    h = bounds.y_max - bounds.y_min
    mx = (bounds.x_min + bounds.x_max) / 2
    my = (bounds.y_min + bounds.y_max) / 2
    if constraints.x_min is not None:
        walls.append(BoxObstacle(constraints.x_min - wt / 2, my, wt, h + 2 * wt))
    if constraints.x_max is not None:
        walls.append(BoxObstacle(constraints.x_max + wt / 2, my, wt, h + 2 * wt))
    if constraints.y_min is not None:
        walls.append(BoxObstacle(mx, constraints.y_min - wt / 2, w + 2 * wt, wt))
    if constraints.y_max is not None:
        walls.append(BoxObstacle(mx, constraints.y_max + wt / 2, w + 2 * wt, wt))
    return walls


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
              return_tree=False, margin=OBSTACLE_MARGIN):
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
        if _line_collides((best.x, best.y), (nx, ny), obstacles, margin):
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

def _prune_path(path, obstacles, margin=OBSTACLE_MARGIN):
    """Greedy shortcutting: skip nodes when straight-line connection is free."""
    if len(path) <= 2:
        return list(path)

    result = [path[0]]
    i = 0
    while i < len(path) - 1:
        # Find the furthest node reachable from path[i] via straight line
        j = len(path) - 1
        while j > i + 1:
            if not _line_collides(path[i], path[j], obstacles, margin):
                break
            j -= 1
        result.append(path[j])
        i = j

    return result


# ============================================================================
# Waypoint Zone Optimization
# ============================================================================

def _optimize_connection_points(points, zone_centers, zone_radii, obstacles,
                                margin=OBSTACLE_MARGIN):
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
            if (not _point_collides(candidate[0], candidate[1], obstacles, margin)
                    and not _line_collides(prev, candidate, obstacles, margin)
                    and not _line_collides(candidate, nxt, obstacles, margin)):
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


def _ensure_spline_safety(points, obstacles, max_rounds=5,
                          margin=OBSTACLE_MARGIN):
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
            if _point_collides(float(xs[k]), float(ys[k]), obstacles, margin):
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

def _subdivide_polyline(points, max_seg_length):
    """Subdivide polyline segments so no segment exceeds max_seg_length."""
    result = [points[0]]
    for i in range(len(points) - 1):
        p1, p2 = points[i], points[i + 1]
        seg_len = _dist(p1, p2)
        n_sub = max(1, int(math.ceil(seg_len / max_seg_length)))
        for j in range(1, n_sub + 1):
            t = j / n_sub
            result.append((
                p1[0] + t * (p2[0] - p1[0]),
                p1[1] + t * (p2[1] - p1[1]),
            ))
    return result


def plan_path(
    start: tuple[float, float],
    end: tuple[float, float],
    waypoints: list[Waypoint] | None = None,
    obstacles: list[Obstacle] | None = None,
    bounds: Bounds | None = None,
    state_constraints: StateConstraints | None = None,
    padding: float = 0.0,
    smoothing: float = 1.0,
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
        BoxObstacle supports rotation via the psi parameter (radians).
    bounds : Bounds, optional
        Workspace limits (converted to wall obstacles).
        If None, inferred from points with padding.
    state_constraints : StateConstraints, optional
        Per-axis position constraints (x_min, x_max, y_min, y_max).
        Only non-None fields are enforced. Converted to wall obstacles
        and also used to restrict RRT sampling for efficiency.
    padding : float
        Robot half-width [m]. Inflates all obstacles by this amount so the
        planned path keeps at least this distance from obstacle surfaces
        (on top of the built-in OBSTACLE_MARGIN). Default 0.0.
    smoothing : float
        Controls how closely the final spline follows the collision-free
        polyline. Range [0, 1]:
        - 1.0 (default): maximum smoothing — spline interpolates only the
          polyline vertices; curves are smooth but may deviate from the
          straight-line polyline.
        - 0.0: minimum smoothing — polyline is densely subdivided before
          spline fitting, so the spline nearly traces the polyline.
        Values in between blend linearly.
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
    smoothing = max(0.0, min(1.0, smoothing))
    margin = OBSTACLE_MARGIN + max(0.0, padding)

    # Infer bounds if not provided
    if bounds is None:
        all_x = [start[0], end[0]] + [wp.x for wp in waypoints]
        all_y = [start[1], end[1]] + [wp.y for wp in waypoints]
        pad = 2.0
        bounds = Bounds(min(all_x) - pad, max(all_x) + pad,
                        min(all_y) - pad, max(all_y) + pad)

    all_obstacles = obstacles + _bounds_to_walls(bounds)

    # Apply state constraints
    if state_constraints is not None:
        all_obstacles += _state_constraints_to_walls(state_constraints, bounds)
        eff_bounds = Bounds(
            max(bounds.x_min, state_constraints.x_min) if state_constraints.x_min is not None else bounds.x_min,
            min(bounds.x_max, state_constraints.x_max) if state_constraints.x_max is not None else bounds.x_max,
            max(bounds.y_min, state_constraints.y_min) if state_constraints.y_min is not None else bounds.y_min,
            min(bounds.y_max, state_constraints.y_max) if state_constraints.y_max is not None else bounds.y_max,
        )
    else:
        eff_bounds = bounds

    # Validate start/end
    if _point_collides(start[0], start[1], all_obstacles, margin):
        raise ValueError(f"Start {start} is inside an obstacle or out of bounds")
    if _point_collides(end[0], end[1], all_obstacles, margin):
        raise ValueError(f"End {end} is inside an obstacle or out of bounds")

    # Trivial case: start ≈ end
    if _dist(start, end) < 1e-6 and not waypoints:
        if debug:
            return PlanResult(
                path=[start], start=start, end=end, waypoints=waypoints,
                obstacles=obstacles, bounds=bounds, padding=padding,
                state_constraints=state_constraints,
                rrt_trees=[], rrt_paths=[],
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

        if not _line_collides(seg_start, seg_goal, all_obstacles, margin):
            # Straight line is free
            raw_path = [seg_start, seg_goal]
            connection = seg_goal
            if debug:
                rrt_trees_all.append([])
        else:
            # Need RRT
            if debug:
                raw_path, tree = _rrt_plan(
                    seg_start, seg_goal, goal_r, all_obstacles, eff_bounds, rng,
                    return_tree=True, margin=margin)
                rrt_trees_all.append(tree if tree else [])
            else:
                raw_path = _rrt_plan(
                    seg_start, seg_goal, goal_r, all_obstacles, eff_bounds, rng,
                    margin=margin)

            if raw_path is None:
                raise RuntimeError(
                    f"RRT failed for segment {i}: {seg_start} → {seg_goal}. "
                    f"Try increasing RRT_MAX_ITERATIONS or check obstacles.")

            # For exact targets (radius=0), extend to exact point if possible
            if zone_radii[i + 1] == 0.0 and _dist(raw_path[-1], seg_goal) > 1e-6:
                if not _line_collides(raw_path[-1], seg_goal, all_obstacles, margin):
                    raw_path.append(seg_goal)
                    connection = seg_goal
                else:
                    connection = raw_path[-1]
            else:
                connection = raw_path[-1]

        rrt_paths_all.append(raw_path)

    # ── Phase 2: Prune each segment ──
    pruned_all = [_prune_path(seg, all_obstacles, margin) for seg in rrt_paths_all]

    # Extract connection points from pruned segment endpoints
    conn_before = [pruned_all[0][0]]
    for seg in pruned_all:
        conn_before.append(seg[-1])
    conn_before[0] = start
    conn_before[-1] = end

    # ── Phase 3: Optimize connection points within waypoint zones ──
    conn_after = _optimize_connection_points(
        conn_before, zone_centers, zone_radii, all_obstacles, margin
    )

    # ── Phase 4: Re-plan between optimized points ──
    full_path = []
    for i in range(len(conn_after) - 1):
        p1, p2 = conn_after[i], conn_after[i + 1]

        if _dist(p1, p2) < 1e-6:
            segment = [p1]
        elif not _line_collides(p1, p2, all_obstacles, margin):
            segment = [p1, p2]
        else:
            raw = _rrt_plan(p1, p2, RRT_STEP_SIZE, all_obstacles, eff_bounds, rng,
                            margin=margin)
            if raw is None:
                raise RuntimeError(
                    f"Re-plan failed between optimized points {p1} → {p2}")
            segment = _prune_path(raw, all_obstacles, margin)

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

    # ── Phase 4.5: Smoothing control — subdivide polyline before spline ──
    if smoothing < 1.0 and len(deduped) >= 2:
        # At smoothing=0: max ~1cm between knots (tight to polyline)
        # At smoothing=1: no subdivision (current behavior)
        ds_knot = 0.01 + smoothing * 0.49  # 1cm → 50cm
        deduped = _subdivide_polyline(deduped, ds_knot)

    # ── Phase 5: Spline smoothing with collision safety ──
    cs_x, cs_y, L, final_pts = _ensure_spline_safety(deduped, all_obstacles,
                                                      margin=margin)
    if cs_x is None:
        if debug:
            return PlanResult(
                path=deduped, start=start, end=end, waypoints=waypoints,
                obstacles=obstacles, bounds=bounds, padding=padding,
                state_constraints=state_constraints,
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
            obstacles=obstacles, bounds=bounds, padding=padding,
            state_constraints=state_constraints,
            rrt_trees=rrt_trees_all, rrt_paths=rrt_paths_all,
            pruned_paths=pruned_all,
            connection_points_before=conn_before,
            connection_points_after=conn_after,
            polyline=polyline, spline_curve=spline_curve)

    return final


# ============================================================================
# Visualization — Single Path
# ============================================================================

def _draw_box_patch(ax, obs: BoxObstacle, facecolor='#ff6b6b',
                    edgecolor='#c0392b', alpha=0.6, linewidth=1.5,
                    inflate=0.0):
    """Draw a (possibly rotated) BoxObstacle as a matplotlib patch.
    inflate > 0 expands width/height by 2*inflate (for padding visualization)."""
    import matplotlib.patches as patches
    import matplotlib.transforms as transforms

    w = obs.width + 2 * inflate
    h = obs.height + 2 * inflate
    r = patches.Rectangle(
        (-w / 2, -h / 2), w, h,
        facecolor=facecolor, edgecolor=edgecolor,
        alpha=alpha, linewidth=linewidth,
    )
    t = (transforms.Affine2D()
         .rotate(obs.psi)
         .translate(obs.cx, obs.cy)
         + ax.transData)
    r.set_transform(t)
    ax.add_patch(r)
    return r


def _draw_padding(ax, obstacles, padding):
    """Draw padding envelopes around obstacles."""
    import matplotlib.patches as patches

    if padding <= 0:
        return
    total = OBSTACLE_MARGIN + padding
    for obs in obstacles:
        if isinstance(obs, CircleObstacle):
            p = patches.Circle(
                (obs.cx, obs.cy), obs.radius + total,
                facecolor='#fdcb6e', edgecolor='#f39c12',
                alpha=0.15, linewidth=0.8, linestyle=':')
            ax.add_patch(p)
        elif isinstance(obs, BoxObstacle):
            _draw_box_patch(ax, obs, facecolor='#fdcb6e', edgecolor='#f39c12',
                            alpha=0.15, linewidth=0.8, inflate=total)


def _draw_state_constraints(ax, state_constraints, bounds):
    """Draw state constraint boundaries as shaded forbidden regions."""
    import matplotlib.patches as patches

    if state_constraints is None:
        return

    color = '#e17055'  # coral/orange
    b = bounds

    if state_constraints.x_min is not None:
        ax.axvline(state_constraints.x_min, color=color, linestyle='--',
                   linewidth=1.2, alpha=0.7, zorder=1)
        rect = patches.Rectangle(
            (b.x_min, b.y_min),
            state_constraints.x_min - b.x_min, b.y_max - b.y_min,
            facecolor=color, alpha=0.08, edgecolor='none')
        ax.add_patch(rect)

    if state_constraints.x_max is not None:
        ax.axvline(state_constraints.x_max, color=color, linestyle='--',
                   linewidth=1.2, alpha=0.7, zorder=1)
        rect = patches.Rectangle(
            (state_constraints.x_max, b.y_min),
            b.x_max - state_constraints.x_max, b.y_max - b.y_min,
            facecolor=color, alpha=0.08, edgecolor='none')
        ax.add_patch(rect)

    if state_constraints.y_min is not None:
        ax.axhline(state_constraints.y_min, color=color, linestyle='--',
                   linewidth=1.2, alpha=0.7, zorder=1)
        rect = patches.Rectangle(
            (b.x_min, b.y_min),
            b.x_max - b.x_min, state_constraints.y_min - b.y_min,
            facecolor=color, alpha=0.08, edgecolor='none')
        ax.add_patch(rect)

    if state_constraints.y_max is not None:
        ax.axhline(state_constraints.y_max, color=color, linestyle='--',
                   linewidth=1.2, alpha=0.7, zorder=1)
        rect = patches.Rectangle(
            (b.x_min, state_constraints.y_max),
            b.x_max - b.x_min, b.y_max - state_constraints.y_max,
            facecolor=color, alpha=0.08, edgecolor='none')
        ax.add_patch(rect)


def plot_path(path, start=None, end=None, waypoints=None, obstacles=None,
              bounds=None, state_constraints=None, padding=0.0,
              title="Motion Plan", figsize=(8, 8)):
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
        plot_margin = 0.3
        ax.set_xlim(bounds.x_min - plot_margin, bounds.x_max + plot_margin)
        ax.set_ylim(bounds.y_min - plot_margin, bounds.y_max + plot_margin)

    # State constraints
    if state_constraints and bounds:
        _draw_state_constraints(ax, state_constraints, bounds)

    # Padding envelopes (drawn first, behind obstacles)
    if obstacles and padding > 0:
        _draw_padding(ax, obstacles, padding)

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
                _draw_box_patch(ax, obs)

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
    plot_margin = 0.2
    ax.set_xlim(b.x_min - plot_margin, b.x_max + plot_margin)
    ax.set_ylim(b.y_min - plot_margin, b.y_max + plot_margin)

    # Bounds rectangle
    rect = patches.Rectangle(
        (b.x_min, b.y_min), b.x_max - b.x_min, b.y_max - b.y_min,
        linewidth=1.5, edgecolor='#2d3436', facecolor='none',
        linestyle='--', alpha=0.5)
    ax.add_patch(rect)

    # State constraints
    _draw_state_constraints(ax, result.state_constraints, result.bounds)

    # Padding envelopes (behind obstacles)
    if result.padding > 0:
        _draw_padding(ax, result.obstacles, result.padding)

    # Obstacles
    for obs in result.obstacles:
        if isinstance(obs, CircleObstacle):
            p = patches.Circle(
                (obs.cx, obs.cy), obs.radius,
                facecolor='#ff6b6b', edgecolor='#c0392b',
                alpha=0.5, linewidth=1)
            ax.add_patch(p)
        elif isinstance(obs, BoxObstacle):
            _draw_box_patch(ax, obs, alpha=0.5, linewidth=1)

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


