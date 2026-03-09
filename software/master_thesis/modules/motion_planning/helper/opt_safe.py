from dataclasses import dataclass
import cvxpy as cp
import numpy as np
import math
from abc import abstractmethod, ABC


def svm_separator(path_line_pts, obs_pts):
    """ Create seperating hyperplane between two consecutive points in our geometric solution path and an obstacle.

    Args:
        path_line_pts (_type_): Two (conesecutive) points of geometric solution we are planning the bezier spline-segment for
        obs_pts (_type_): Corner points of an obstacle

    Returns:
        _type_: _description_
    """

    w = cp.Variable(len(path_line_pts[0])) # weight-vector has same dimension as a data point
    b = cp.Variable()

    # positive class must lie at least 1 unit "above" the boundary
    pos_constraints = [ w @ x + b >= 1 for x in path_line_pts ]
    # negative class must lie no farther than 0 ("on or below" the boundary)
    neg_constraints = [ w @ x + b <= 0 for x in obs_pts ]

    prob = cp.Problem(cp.Minimize(cp.sum_squares(w)/2),
                      pos_constraints + neg_constraints)
    prob.solve()
    # Only accept a clean optimal solution. 'optimal_inaccurate' yields garbage
    # hyperplane coefficients that make the Bézier optimization infeasible.
    if prob.status != 'optimal' or w.value is None or b.value is None:
        return None, None
    return w.value, b.value


# ---------------------------------------------------------------------------
# OptimizationData
# ---------------------------------------------------------------------------

@dataclass
class OptimizationData:
    """Structured input for the Bezier / flat-output optimiser.

    Attributes
    ----------
    bound_min:  [x_min, y_min]
    bound_high: [x_max, y_max]
    start:      [x, y]
    goal:       [x, y]
    path:       list of [x, y] waypoints (OMPL output)
    obstacles:  list of [x_min, x_max, y_min, y_max] AABBs
    output_path: optional path for saving figures / YAML exports
    """
    bound_min:    list
    bound_high:   list
    start:        list          
    goal:         list
    path:         list        # waypoints [(x,y), ...]
    obstacles:    list        # AABBs [xmin, xmax, ymin, ymax]
    output_path:  str | None = None
    start_psi:    float | None = None  # agent heading at start (rad); used for heading constraint
    robot_radius: float = 0.0          # bounding radius for sphere approximation (Minkowski sum)


class BezierCalculator():
    # Coefficients matrix according to Bernstein
    _COEFFS = np.array([
        [ 1,  0,  0,  0],
        [-3,  3,  0,  0],
        [ 3, -6,  3,  0],
        [-1,  3, -3,  1],
    ])

    @classmethod
    def bezier_curve(cls, t, control_points):
        """B(t) = [1, t, t^2, t^3] @ _COEFFS @ P"""
        basis = np.array([1, t, t**2, t**3])
        return basis @ cls._COEFFS @ np.array(control_points)

    @classmethod
    def bezier_dot(cls, t, control_points):
        """B'(t) = [0, 1, 2t, 3t^2] @ _COEFFS @ P"""
        basis_dot = np.array([0, 1, 2*t, 3*t**2])
        return basis_dot @ cls._COEFFS @ np.array(control_points)

    @classmethod
    def bezier_ddot(cls, t, control_points):
        """B''(t) = [0, 0, 2, 6t] @ _COEFFS @ P"""
        basis_ddot = np.array([0, 0, 2, 6*t])
        return basis_ddot @ cls._COEFFS @ np.array(control_points)

    @staticmethod
    def dot_bezier_curve(t, control_points):
        basis = np.array([1,t,t**2])
        coeffs = np.array([])

    @classmethod
    def bezier_func(cls, ctrl_pts):
        return lambda t: np.array([cls.bezier_curve(ti, ctrl_pts) for ti in t])

    @staticmethod
    def bezier_dot_func(ctrl_points):
        P0, P1, P2, P3 = ctrl_points
        def func(t):
            t_arr = np.atleast_1d(t)
            t_col = t_arr[:, np.newaxis]
            # compute derivative vector for each t
            return (3 * (1 - t_col)**2 * (P1  - P0) +
                    6 * (1 - t_col) * t_col * (P2 - P1) +
                    3 * t_col**2 * (P3 - P2))
        return func

    @staticmethod
    def bezier_ddot_func(ctrl_points):
        P0, P1, P2, P3 = ctrl_points
        def func(t):
            t_arr = np.atleast_1d(t)
            t_col = t_arr[:, np.newaxis]
            # compute second derivative vector for each t
            return (6 * (1 - t_col) * (P2 - 2 * P1 + P0) +
                    6 * t_col * (P3 - 2 * P2 + P1))
        return func

    @classmethod
    def eval_bezier_length(cls, control_points):
        t_vals = np.linspace(0, 1, 15)
        points = cp.vstack([cls.bezier_curve(t, control_points) for t in t_vals])
        lengths = cp.norm(cp.diff(points, axis=0), axis=1)
        return cp.sum(lengths)

    @classmethod
    def eval_bezier_curvature(cls, ctrl_points):
        t_vals = np.linspace(0, 1, 100)
        points = cp.vstack([cls.bezier_ddot(t, ctrl_points) for t in t_vals])
        lengths = cp.norm(cp.diff(points, axis=0), axis=1)
        return cp.sum(lengths)

    @classmethod
    def z_dz_ddz_discrete(cls, t_discrete:np.ndarray, control_points:list[list[np.ndarray]])-> tuple[np.ndarray, np.ndarray, np.ndarray]:
        # T = t_discrete[-1] # get max time
        t_discrete = np.array(t_discrete)

        z_funcs = []
        dot_z_funcs = []
        ddot_z_funcs = []


        for control_point_set in control_points:
            z_funcs.append(cls.bezier_func(control_point_set)) # get piecewise function
            dot_z_funcs.append(cls.bezier_dot_func(control_point_set))
            ddot_z_funcs.append(cls.bezier_ddot_func(control_point_set))

        # approximate numeric segment lengths by sampling each bezier curve
        segment_lengths = []
        num_samples = 100
        for pts in control_points:
            t_samples = np.linspace(0, 1, num=num_samples)
            curve_points = cls.bezier_func(pts)(t_samples)
            diffs = np.diff(curve_points, axis=0)
            lengths = np.linalg.norm(diffs, axis=1)
            segment_lengths.append(np.sum(lengths))

        # assign segment durations proportional to lengths so sum matches total time horizon
        total_time = t_discrete[-1] - t_discrete[0]
        total_length = sum(segment_lengths)
        segment_durations = [L / total_length * total_time for L in segment_lengths]

        z_vals, dot_z_vals, ddot_z_vals = [], [], []
        t_current = 0

        for _, (z_f, dz_f, ddz_f, T_i) in enumerate(zip(z_funcs, dot_z_funcs, ddot_z_funcs, segment_durations)):
            mask = np.logical_and(t_discrete >= t_current, t_discrete <= t_current + T_i)
            t_segment = t_discrete[mask]
            t_local = (t_segment - t_current) / T_i  # normalize to [0, 1]

            z_vals.append(z_f(t_local))
            dot_z_vals.append(dz_f(t_local) / T_i)
            ddot_z_vals.append(ddz_f(t_local) / T_i**2)

            t_current += T_i

        return np.vstack(z_vals), np.vstack(dot_z_vals), np.vstack(ddot_z_vals)



class Plotter:

    @staticmethod
    def plot_environment(ax, bound_min, bound_high, obstacles):
        import matplotlib.patches as patches
        for obstacle in obstacles:
            ax.add_patch(patches.Rectangle((obstacle[0], obstacle[2]),
                                        obstacle[1] - obstacle[0],
                                        obstacle[3] - obstacle[2],
                                        angle=0.25, linewidth=2, edgecolor='b', facecolor='b', alpha=0.4))
        ax.set_xlim(bound_min[0], bound_high[0])
        ax.set_ylim(bound_min[1], bound_high[1])

    @staticmethod
    def plot_beziers(ax, curve_functions, colors):

        t = np.linspace(0, 1, num=256)
        discrete_curves = []
        for curve_function in curve_functions:
            # evaluate discrete points of curve
            curve_points = curve_function(t)
            discrete_curves.append(curve_points)

        for curve, color in zip(discrete_curves, colors):
            x_vals = [point[0] for point in curve]
            y_vals = [point[1] for point in curve]
            ax.plot(x_vals, y_vals, color=color)

    @staticmethod
    def set_colors(curve_functions):
        import matplotlib.pyplot as plt
        
        return list(plt.cm.Reds(np.linspace(0.3, 1, len(curve_functions))))

    @staticmethod
    def plot_hyperplanes(ax, hyperplane_regions, bound_min, bound_high, colors):
        for safe_region, bound_min, bound_high, color in zip(hyperplane_regions, bound_min, bound_high, colors):
            for hyperplane in safe_region:
                try:
                    x = np.linspace(bound_min[0], bound_high[0], 100)
                    y = -(hyperplane[0][0] * x + hyperplane[1]) / hyperplane[0][1]
                    ax.plot(x, y, color=color, linestyle='dashed')
                except:
                    pass


    @staticmethod
    def plot_path_points(path, ax, colors=None):
        # Each segment i spans path[i] → path[i+1] and has color colors[i].
        # Assign point i the color of segment i (last point gets color of last segment).
        for i, point in enumerate(path):
            color = colors[min(i, len(colors) - 1)] if colors is not None else 'black'
            ax.plot(point[0], point[1], marker='o', color=color, markersize=6,
                    markeredgecolor='black', markeredgewidth=0.8)

    @classmethod
    def assignment04_plot(cls, ax, setup, curve_functions, hyperplanes):
        colors = cls.set_colors(curve_functions)
        cls.plot_environment(ax, setup.bound_min, setup.bound_high, setup.obstacles)
        cls.plot_beziers(ax, curve_functions, colors)
        cls.plot_hyperplanes(
            ax,
            hyperplanes,
            [setup.bound_min] * len(hyperplanes),
            [setup.bound_high] * len(hyperplanes),
            colors
        )
        cls.plot_path_points(setup.path, ax, colors=colors)


class OptSafeBase:

    def __init__(self, data: OptimizationData) -> None:
        self.setup = data
        self.variables = []
        self.constraints = []
        self.feasible = True
        self.hyperplanes = []
        self.curve_function_segments = [] # individual bezier curves for piecewise path
        self.control_points = [] # just for computing derivatives in case flat output used

    def find_hyperplanes(self):
        """Use SVM to get hyperplanes (safe regions) for each curve segment.

        When SVM is infeasible (path waypoints and obstacle corners are not
        linearly separable — typically because the path grazes a corner), we
        fall back to an axis-aligned face constraint: find the AABB face that
        BOTH path endpoints are clearly outside of, then add the corresponding
        half-space.

        Requiring both endpoints (not just the midpoint) ensures that the
        start-pin constraint (P0 == path[i]) never conflicts with the
        face constraint — if path[i] is not outside the face, we don't add
        the face constraint at all.

        The Bézier convex-hull property guarantees that if all control points
        satisfy the half-space, the full smooth curve does too.
        """
        self.hyperplanes = []
        for i in range(len(self.setup.path) - 1): # For each geoemtric point
            hyperplanes_for_segment = []
            pa = self.setup.path[i]
            pb = self.setup.path[i + 1]
            
            for obstacle in self.setup.obstacles:  # [xmin, xmax, ymin, ymax]
                xmin, xmax, ymin, ymax = obstacle
                corners = [[obstacle[j % 2], obstacle[2 + (j // 2)]] for j in range(4)]
                w, b = svm_separator(self.setup.path[i:i+2], corners)
                if w is None:
                    # SVM infeasible: path grazes an obstacle corner.
                    # Fall back to an axis-aligned face constraint, but only
                    # add one if BOTH endpoints are clearly outside that face.
                    # This prevents the face constraint from conflicting with
                    # the pin constraint P0 == path[i].
                    candidates = []
                    if pa[0] >= xmax and pb[0] >= xmax:  # both right of right face
                        candidates.append((min(pa[0] - xmax, pb[0] - xmax),
                                           np.array([1., 0.]), -xmax))
                    if pa[0] <= xmin and pb[0] <= xmin:  # both left of left face
                        candidates.append((min(xmin - pa[0], xmin - pb[0]),
                                           np.array([-1., 0.]), xmin))
                    if pa[1] >= ymax and pb[1] >= ymax:  # both above top face
                        candidates.append((min(pa[1] - ymax, pb[1] - ymax),
                                           np.array([0., 1.]), -ymax))
                    if pa[1] <= ymin and pb[1] <= ymin:  # both below bottom face
                        candidates.append((min(ymin - pa[1], ymin - pb[1]),
                                           np.array([0., -1.]), ymin))
                    if candidates:
                        _, w_fb, b_fb = max(candidates, key=lambda t: t[0])
                        hyperplanes_for_segment.append([w_fb, b_fb])
                    # else: no consistent face found — skip this obstacle for this segment
                    continue
                hyperplanes_for_segment.append([w, b])
            self.hyperplanes.append(hyperplanes_for_segment)

    def create_optimization_vars(self):
        for _ in range(len(self.setup.path) - 1):
            p0, p1, p2, p3 = cp.Variable(2), cp.Variable(2), cp.Variable(2), cp.Variable(2)
            self.variables.append([p0, p1, p2, p3])

    def create_bezier(self):
        if not self.feasible:
            print("Given path is invalid")
            return

        self.constraints = []

        # Start / goal / intermediate waypoint pins
        self.constraints.append(self.variables[0][0] == self.setup.start)
        self.constraints.append(self.variables[-1][-1] == self.setup.goal)
        for i in range(len(self.variables) - 1):
            self.constraints.append(self.variables[i][-1] == self.setup.path[i + 1])

        # SVM half-space constraints with sphere approximation.
        # Free inner control points (P1, P2) are shifted by r so the full
        # Bézier curve (which lies inside the control-point convex hull) keeps
        # the robot body clear of each separating hyperplane.
        # Pinned endpoints (P0, P3) are OMPL waypoints already verified by FCL,
        # so they only need the basic >= 0 half-space.
        r = float(getattr(self.setup, 'robot_radius', 0.0))
        PINNED = {0, 3}
        for i, curve_params in enumerate(self.variables):
            for j, variable in enumerate(curve_params):
                for hyperplane in self.hyperplanes[i]:
                    w, b = hyperplane[0], hyperplane[1]
                    norm_w = float(np.linalg.norm(w))
                    margin = 0.0 if j in PINNED else r * norm_w
                    self.constraints.append(variable @ w + b >= margin)
                self.constraints.append(variable <= self.setup.bound_high)
                self.constraints.append(variable >= self.setup.bound_min)

        # C0 / C1 / C2 continuity at segment junctions
        for i in range(len(self.variables) - 1):
            p, q = self.variables[i], self.variables[i + 1]
            self.constraints.append(q[0] == p[3])
            self.constraints.append(p[2] - p[3] == q[0] - q[1])
            self.constraints.append(p[1] - 2 * p[2] + p[3] == q[0] - 2 * q[1] + q[2])

        total_length = sum(BezierCalculator.eval_bezier_length(v) for v in self.variables)
        prob = cp.Problem(cp.Minimize(total_length), self.constraints)
        prob.solve(verbose=False)

        if prob.status not in ('optimal', 'optimal_inaccurate'):
            self.feasible = False
            return

        for p in self.variables:
            ctrl_pts = [pi.value for pi in p]
            self.control_points.append(ctrl_pts)
            self.curve_function_segments.append(BezierCalculator.bezier_func(ctrl_pts))

    def get_discretized_path(self, num_points=256):
        t_vals = np.linspace(0, 1, num=num_points)
        path = []
        for p in self.variables:
            ctrl_pts = [pi.value for pi in p]
            path.append([bezier_curve(t, ctrl_pts) for t in t_vals])
        return path

    def get_points(self, w, b):
        if not math.isclose(w[1], 0, rel_tol=1e-8, abs_tol=1e-8):
            return [[self.setup.bound_min[0], -(w[0] * self.setup.bound_min[0] + b) / w[1]],
                    [self.setup.bound_high[0], -(w[0] * self.setup.bound_high[0] + b) / w[1]]]
        else:
            return [[-(w[1] * self.setup.bound_min[1] + b) / w[0], self.setup.bound_min[1]],
                    [-(w[1] * self.setup.bound_high[1] + b) / w[0], self.setup.bound_high[1]]]

    def create_plot(self):
        try:
            import matplotlib.pyplot as plt
            import matplotlib.patches as patches
        except ImportError:
            print('matplotlib not available, skipping plot creation')
            return

        print('creating the plot')
        fig, ax = plt.subplots()
        Plotter.assignment04_plot(ax, self.setup, self.curve_function_segments, self.hyperplanes)
        plt.show()

    @abstractmethod
    def create_plan_content(self)-> dict:
        ...

    @abstractmethod
    def bezier_to_configurations(self):
        ...


class FlatOutputOpt(OptSafeBase, ABC):
    def __init__(self, data: OptimizationData, dt: float = 0.1, T_guess: float = 10) -> None:
        super().__init__(data)
        self.dt = dt
        self.T_guess = T_guess  # updated by bezier_to_configurations() after temporal scaling
        self.actions = None
        self.states  = None
        self.type    = None     # subclasses set e.g. 'car', 'frodo'

    @abstractmethod
    def check_validity_actions(self, actions)->bool:
        ...

    @staticmethod
    @abstractmethod
    def compute_states(z, dot_z, ddot_z)-> np.ndarray:
        ...

    @abstractmethod
    def compute_actions(self, z, dot_z, ddot_z) -> np.ndarray:
        ...

    def inverse_flatness(self, timesteps, z, dot_z, ddot_z):

        states = self.compute_states(z, dot_z, ddot_z)
        actions = self.compute_actions(z, dot_z, ddot_z)

        return states, actions

    def bezier_to_configurations(self):
        T = self.T_guess
        actions = []
        states = []
        iter_count = 0
        if not self.control_points:
            raise RuntimeError('Optimization not executed yet')

        valid_actions = False # check if temporal scaling needs to be done
        while valid_actions is not True:

            discrete_time_horizon = np.arange(0, T, self.dt)

            z, dot_z, ddot_z = BezierCalculator.z_dz_ddz_discrete(discrete_time_horizon, self.control_points)

            states, actions = self.inverse_flatness(discrete_time_horizon, z, dot_z, ddot_z)

            valid_actions = self.check_validity_actions(actions)

            if not valid_actions:
                T = 1.1 * T

            iter_count += 1

        # Store the final time horizon so get_trajectory() can resample at any dt
        self.T_guess = T
        self.actions = actions
        self.states  = states

    def get_trajectory(self, dt: float) -> tuple[np.ndarray, np.ndarray]:
        """Return (states, actions) sampled at *dt* after bezier_to_configurations().

        Must be called after bezier_to_configurations(), which sets the final
        self.T_guess via temporal scaling.

        Returns
        -------
        states:  np.ndarray, shape (N+1, 3) — [x, y, psi] at each sample
        actions: np.ndarray, shape (N, 2)   — [v, psi_dot] between samples
        """
        if not self.control_points:
            raise RuntimeError('Call create_bezier() then bezier_to_configurations() first.')

        # N+1 time samples: include both endpoints of the full time horizon
        t_full = np.arange(0, self.T_guess + dt / 2, dt)
        z, dz, ddz = BezierCalculator.z_dz_ddz_discrete(t_full, self.control_points)

        states  = self.compute_states(z, dz, ddz)    # (N+1, 3)
        actions = self.compute_actions(z, dz, ddz)    # (N+1, 2) — drop last
        return states, actions[:-1]                   # (N+1, 3), (N, 2)

    @abstractmethod
    def create_plan_content(self) -> dict:
        ...
            
# ---------------------------------------------------------------------------
# FRODOFlatOpt — unicycle flat-output inversion (zero-wheelbase limiting case)
# ---------------------------------------------------------------------------

class FRODOFlatOpt(FlatOutputOpt):
    """Flat-output Bezier optimiser for the FRODO unicycle robot.

    Control laws (flat-output inversion):
        v       = sqrt(ẋ² + ẏ²)
        ψ       = atan2(ẏ, ẋ)
        ψ_dot   = (ÿẋ − ẋÿ) / (ẋ² + ẏ²)

    Parameters
    ----------
    data:        OptimizationData or YAML path
    dt:          Simulation timestep (used in bezier_to_configurations)
    v_max:       Maximum forward speed [m/s]
    psi_dot_max: Maximum yaw rate [rad/s]
    T_guess:     Initial time-horizon guess for temporal scaling
    """

    def __init__(self, data: OptimizationData, dt: float = 0.1,
                 v_max: float = 1.0, psi_dot_max: float = np.pi / 3,
                 T_guess: float = 10) -> None:
        super().__init__(data, dt=dt, T_guess=T_guess)
        self.v_max       = v_max
        self.psi_dot_max = psi_dot_max
        self.type        = 'frodo'

    @staticmethod
    def compute_states(z, dot_z, ddot_z) -> np.ndarray:
        """Map flat output to [x, y, psi] states."""
        psi = np.arctan2(dot_z[:, 1], dot_z[:, 0])
        return np.stack((z[:, 0], z[:, 1], psi), axis=1)

    def compute_actions(self, z, dot_z, ddot_z) -> np.ndarray:
        """Map flat output to [v, psi_dot] actions."""
        vx, vy = dot_z[:, 0], dot_z[:, 1]
        ax, ay = ddot_z[:, 0], ddot_z[:, 1]

        v     = np.sqrt(vx**2 + vy**2)
        denom = vx**2 + vy**2
        # Guard against division by zero at near-zero speed
        psi_dot = np.where(denom > 1e-6, (ay * vx - vy * ax) / denom, 0.0)

        return np.stack((v, psi_dot), axis=1)

    def check_validity_actions(self, actions: np.ndarray) -> bool:
        v_ok       = np.all(np.abs(actions[:, 0]) <= self.v_max)
        psi_dot_ok = np.all(np.abs(actions[:, 1]) <= self.psi_dot_max)
        return bool(v_ok and psi_dot_ok)

    def bezier_to_configurations(self):
        """Time-optimal pointwise velocity profile (continuous TOPP).

        At every point s on each Bézier segment, compute the maximum parameter
        speed ṡ that satisfies both constraints simultaneously:

            ṡ_max(s) = min( v_max / |z'(s)|,  ψ̇_max / |κ(s)| )

        where κ(s) = (z''_y · z'_x - z'_y · z''_x) / |z'|²  is the local
        curvature in s-space (ψ̇ per unit ṡ).

        Integrating dt = ds / ṡ_max gives the time-optimal axis without
        iteration, replacing the global scaling while-loop in the base class.
        """
        if not self.control_points:
            raise RuntimeError('Optimization not executed yet')

        N_s = 500
        s   = np.linspace(0, 1, N_s)
        ds  = s[1] - s[0]

        t_pieces       = []
        z_pieces       = []
        v_pieces       = []
        psi_pieces     = []
        psi_dot_pieces = []
        t_offset       = 0.0

        for ctrl_pts in self.control_points:
            z_s   = BezierCalculator.bezier_func(ctrl_pts)(s)       # (N_s, 2)
            zp_s  = BezierCalculator.bezier_dot_func(ctrl_pts)(s)   # (N_s, 2)  z'  = dz/ds
            zpp_s = BezierCalculator.bezier_ddot_func(ctrl_pts)(s)  # (N_s, 2)  z'' = d²z/ds²

            speed = np.linalg.norm(zp_s, axis=1)                    # |z'(s)|
            denom = np.maximum(speed**2, 1e-8)

            # κ(s) = (z''_y · z'_x - z'_y · z''_x) / |z'|²  — ψ̇ per unit ṡ
            kappa = (zpp_s[:, 1] * zp_s[:, 0] - zp_s[:, 1] * zpp_s[:, 0]) / denom

            # maximum parameter speed satisfying both constraints pointwise
            s_dot_max = np.minimum(
                self.v_max       / np.maximum(speed,          1e-8),
                self.psi_dot_max / np.maximum(np.abs(kappa), 1e-8),
            )

            # integrate dt = ds / ṡ_max → cumulative local time
            dt_arr = ds / np.maximum(s_dot_max, 1e-8)
            t_seg  = np.concatenate([[0.0], np.cumsum(dt_arr[:-1])])

            t_pieces.append(t_seg + t_offset)
            z_pieces.append(z_s)
            v_pieces.append(speed * s_dot_max)           # v   = |z'| · ṡ
            psi_pieces.append(np.arctan2(zp_s[:, 1], zp_s[:, 0]))
            psi_dot_pieces.append(kappa * s_dot_max)     # ψ̇  = κ · ṡ

            t_offset += float(t_seg[-1])

        # Concatenate, dropping duplicate junction points
        def _cat(pieces):
            return np.concatenate([pieces[0]] + [p[1:] for p in pieces[1:]])

        t_all       = _cat(t_pieces)
        z_all       = np.vstack([z_pieces[0]] + [z[1:] for z in z_pieces[1:]])
        v_all       = _cat(v_pieces)
        psi_all     = np.unwrap(_cat(psi_pieces))  # unwrap for smooth interpolation
        psi_dot_all = _cat(psi_dot_pieces)

        self.T_guess      = float(t_all[-1])
        self._t_opt       = t_all
        self._z_opt       = z_all
        self._v_opt       = v_all
        self._psi_opt     = psi_all
        self._psi_dot_opt = psi_dot_all

        # populate self.states / self.actions at self.dt for backward compatibility
        self.states, self.actions = self.get_trajectory(self.dt)

    def get_trajectory(self, dt: float) -> tuple[np.ndarray, np.ndarray]:
        """Resample the optimal trajectory at a uniform timestep dt."""
        if not hasattr(self, '_t_opt'):
            raise RuntimeError('Call bezier_to_configurations() first.')

        t = np.arange(0, self.T_guess + dt / 2, dt)

        x       = np.interp(t, self._t_opt, self._z_opt[:, 0])
        y       = np.interp(t, self._t_opt, self._z_opt[:, 1])
        psi     = np.interp(t, self._t_opt, self._psi_opt)
        psi     = (psi + np.pi) % (2 * np.pi) - np.pi  # re-wrap to [-π, π]
        v       = np.interp(t, self._t_opt, self._v_opt)
        psi_dot = np.interp(t, self._t_opt, self._psi_dot_opt)

        states  = np.stack([x, y, psi], axis=1)   # (N+1, 3)
        actions = np.stack([v, psi_dot], axis=1)   # (N+1, 2)
        return states, actions[:-1]                # (N+1, 3), (N, 2)

    def create_plan_content(self) -> dict:
        # Not used in the FRODO simulation pipeline (trajectory goes via MPPhaseContainer)
        return {}


def main():
    """
    Standalone execution for OptSafe without OMPL.
    Demonstrates the full Bezier pipeline using OptimizationData.
    """
    opt_data = OptimizationData(
        bound_min=[0.0, 0.0],
        bound_high=[10.0, 10.0],
        start=[1.0, 1.0],
        goal=[9.0, 9.0],
        path=[
            [1.0, 1.0],
            [2.0, 3.0],
            [7.0, 3.0],
            [9.0, 9.0],
        ],
        obstacles=[
            [4.0, 6.0, 4.0, 6.0],   # [xmin, xmax, ymin, ymax]
            [2.5, 3.5, 6.0, 8.0],
        ],
    )

    opt = FRODOFlatOpt(data=opt_data, dt=0.1)

    opt.find_hyperplanes()
    opt.create_optimization_vars()
    opt.create_bezier()
    opt.bezier_to_configurations()

    print("===== Optimization Done =====")
    print(f"Number of Bezier segments: {len(opt.control_points)}")
    print(f"States shape: {np.array(opt.states).shape}")
    print(f"Actions shape: {np.array(opt.actions).shape}")

    # get_trajectory demo
    states, actions = opt.get_trajectory(dt=0.1)
    print(f"get_trajectory → states {states.shape}, actions {actions.shape}")

    try:
        opt.create_plot()
    except Exception as e:
        print("Plotting failed:", e)


if __name__ == "__main__":
    main()
