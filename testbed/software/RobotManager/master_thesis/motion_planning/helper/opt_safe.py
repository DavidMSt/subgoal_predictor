from dataclasses import dataclass
import cvxpy as cp
import numpy as np
import math
import yaml
from abc import abstractmethod, ABC


def svm_separator(line_pts, obs_pts):
    
    w = cp.Variable(len(line_pts))
    b = cp.Variable()

    # positive class must lie at least 1 unit “above” the boundary
    pos_constraints = [ w @ x + b >= 1 for x in line_pts ]
    # negative class must lie no farther than 0 (“on or below” the boundary)
    neg_constraints = [ w @ x + b <= 0 for x in obs_pts ]

    prob = cp.Problem(cp.Minimize(cp.sum_squares(w)/2),
                      pos_constraints + neg_constraints)
    prob.solve()
    return w.value, b.value

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
        t_vals = np.linspace(0, 1, 100)
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

        # for z_f, dz_f, ddz_f, T_i in zip(z_funcs, dot_z_funcs, ddot_z_funcs, segment_durations):
            # print("laenge: ", len(z_funcs))
            # print(T_i.shape)
            # print(T_i)
            # print(type(segment_durations[0]))
            # raise KeyError

        for _, (z_f, dz_f, ddz_f, T_i) in enumerate(zip(z_funcs, dot_z_funcs, ddot_z_funcs, segment_durations)):
            mask = np.logical_and(t_discrete >= t_current, t_discrete <= t_current + T_i)
            t_segment = t_discrete[mask]
            t_local = (t_segment - t_current) / T_i  # normalize to [0, 1]
            
            z_vals.append(z_f(t_local))
            dot_z_vals.append(dz_f(t_local) / T_i)
            ddot_z_vals.append(ddz_f(t_local) / T_i**2)
            
            t_current += T_i

        return np.vstack(z_vals), np.  vstack(dot_z_vals), np.vstack(ddot_z_vals)


@dataclass
class OptimizerSetup():
    def __init__(self, env_path, out_path) -> None:
        with open(env_path, "r") as file:
            in_args = yaml.safe_load(file)
        
        self.output_path = out_path
        env = in_args["environment"]
        motion = in_args["motionplanning"]
        
        self.bound_min = env["min"][:2] # ignore z coordinate for all here
        self.bound_high = env["max"][:2]
        self.start = motion["start"][:2]
        self.goal = motion["goal"][:2]
        self.path = [path[:2] for path in motion["solutionpath"]] 
        
        self.obstacles = [[obs["pos"][0] - obs["size"][0] / 2, 
                        obs["pos"][0] + obs["size"][0] / 2, 
                        obs["pos"][1] - obs["size"][1] / 2, 
                        obs["pos"][1] + obs["size"][1] / 2]
                        for obs in env["obstacles"] if obs is not None]
        
class Plotter:

    @staticmethod
    def plot_environment(ax, bound_min, bound_high, obstacles):
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
    def plot_path_points(path, ax):
        for point in path:
                ax.plot(point[0], point[1], marker='o', color='black', markersize=4)

    @staticmethod
    def save_figure(fig, output_path):
        print('saving the figure')
        fig.savefig(output_path)

    @classmethod
    def assignment04_plot(cls, ax, fig, setup, curve_functions, hyperplanes, save_fig = True, output_path = None):
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
        cls.plot_path_points(setup.path, ax)
        if save_fig:
            cls.save_figure(fig, output_path)


class OptSafeBase:

    def __init__(self, env_path: str,) -> None:
        self.setup = OptimizerSetup(env_path)
        self.variables = []
        self.constraints = []
        self.feasible = True
        self.hyperplanes = []
        self.curve_function_segments = [] # individual bezier curves for piecewise path
        self.control_points = [] # just for computing derivatives in case flat output used

    def find_hyperplanes(self):
        """_summary_ Use SVM to get hyperplanes (safe regions) for each curve segment
        """
        self.hyperplanes = []
        for i in range(len(self.setup.path) - 1):
            hyperplanes_for_segment = []
            for obstacle in self.setup.obstacles:  # [xmin, xmax, ymin, ymax]
                corners = [[obstacle[j % 2], obstacle[2 + (j // 2)]] for j in range(4)]
                w, b = svm_separator(self.setup.path[i:i+2], corners)
                hyperplanes_for_segment.append([w, b])
                if w is None:
                    self.feasible = False
                    break  # If one hyperplane fails, no need to continue
            self.hyperplanes.append(hyperplanes_for_segment)

    def create_optimization_vars(self):
        for _ in range(len(self.setup.path) - 1):
            p0, p1, p2, p3 = cp.Variable(2), cp.Variable(2), cp.Variable(2), cp.Variable(2)
            self.variables.append([p0, p1, p2, p3])

    def create_bezier(self):
        def add_start_goal_constraints():
            self.constraints.append(self.variables[0][0] == self.setup.start)
            self.constraints.append(self.variables[-1][-1] == self.setup.goal)
        
        def add_hyperplane_constraints():
            # SVM / boundaries
            for i, curve_params in enumerate(self.variables):
                for variable in curve_params:
                    for hyperplane in self.hyperplanes[i]:
                        self.constraints.append(variable @ hyperplane[0] + hyperplane[1] >= 0)
                    self.constraints.append(variable <= self.setup.bound_high)
                    self.constraints.append(variable >= self.setup.bound_min)

        # def add_curvature_constraints():
        #     phi_max = np.pi/6
        #     k_max = np.tan(phi_max) / self.L
        #     n_samples = 10
        #     t_vals = np.linspace(0, 1, n_samples)
        #     for ctrl_pts in self.variables:
        #         for t_i in t_vals:
        #             dd = BezierCalculator.bezier_ddot(t_i, ctrl_pts)
        #             self.constraints.append(cp.norm(dd, 2) <= k_max)

        def add_continuity_constraints():
            # Continuity
            for i in range(len(self.variables) - 1):
                p = self.variables[i]
                q = self.variables[i + 1]
                self.constraints.append(q[0] == p[3])
                self.constraints.append(p[2] - p[3] == q[0] - q[1])
                self.constraints.append(p[1] - 2 * p[2] + p[3] == q[0] - 2 * q[1] + q[2])

        def calculate_bezier_length():
            # Calculate the approximate length of each of the three b-splines
            length_p = BezierCalculator.eval_bezier_length(self.variables[0])
            length_q = BezierCalculator.eval_bezier_length(self.variables[1])
            length_r = BezierCalculator.eval_bezier_length(self.variables[2])

            return length_p+ length_q + length_r
        
        def calculate_bezier_curvature():
            # Calculate the approximate curvature of each of the three b-splines
            curve_p = BezierCalculator.eval_bezier_curvature(self.variables[0])
            curve_q = BezierCalculator.eval_bezier_curvature(self.variables[1])
            curve_r = BezierCalculator.eval_bezier_curvature(self.variables[2])

            return curve_p+ curve_q + curve_r
        
        def calculate_bezier_curvature_max():
            # convex surrogate for max curvature: sample second derivative norms and take maximum
            n_samples = 10
            t_vals = np.linspace(0, 1, n_samples)
            curv_samples = []
            for ctrl_pts in self.variables:
                for t_i in t_vals:
                    dd = BezierCalculator.bezier_ddot(t_i, ctrl_pts)
                    curv_samples.append(cp.norm(dd, 2))
            # stack into one vector and extract maximum entry
            curv_vec = cp.hstack(curv_samples)
            return cp.max(curv_vec)

        if self.feasible:
            # add constraints for optimization
            add_start_goal_constraints()
            add_hyperplane_constraints()
            add_continuity_constraints()
            # add_curvature_constraints()

            # calculate total length of bezier curve
            total_length = calculate_bezier_length()

            # calculate curvature of complete bezire curve
            bezier_curvature = calculate_bezier_curvature()

            # calculate max min curvature
            bezier_max_min_curv = calculate_bezier_curvature_max()
            
            # perform optimization
            # obj = cp.Minimize(total_length + 1* bezier_curvature + 1 * bezier_max_min_curv)
            obj = cp.Minimize(total_length)
            prob = cp.Problem(obj, self.constraints)
            prob.solve(verbose=True)

            for p in self.variables:
                ctrl_pts = [pi.value for pi in p]
                self.control_points.append(ctrl_pts)
                curve_function = BezierCalculator.bezier_func(ctrl_pts)
                self.curve_function_segments.append(curve_function)
                

        else:
            print("Given path is invalid")

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
        
    # def discretize_bezier(self, control_points, dt):
    #     t_values = np.arange(0, 1 + dt, dt)
    #     return [bezier_curve(t, control_points) for t in t_values]
    
    def create_plot(self):
        if not HAS_MATPLOTLIB:
            print('matplotlib not available, skipping plot creation')
            return
        
        print('creating the plot')
        fig, ax = plt.subplots()
        Plotter.assignment04_plot(ax, fig, self.setup, self.curve_function_segments, self.hyperplanes, True, self.setup.output_path)
        #plt.show()

    @abstractmethod
    def create_plan_content(self)-> dict:
        ...

    @abstractmethod
    def bezier_to_configurations(self):
        ...

    def export_to_yaml(self):
        print('here')
        if not self.yaml_export_path:
            print('no path is set')
            return
        plan_content = self.create_plan_content()
        
        with open(self.yaml_export_path, 'w') as file:
            yaml.dump(plan_content, file, default_flow_style=None, sort_keys=False)

        print('exported yaml file')

class FlatOutputOpt(OptSafeBase, ABC):
    def __init__(self, env_path: str, dt = 0.1, yaml_export_path= None, T_guess = 10) -> None:
        super().__init__(env_path, yaml_export_path)
        self.dt = dt
        self.actions = None
        self.states = None
        self.type = None # e.g. arm, car
        self.T_guess = T_guess # initial guess for time horizon, if constraints not met, apply temporal scaling
    
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

            print('current iteration of temporal scaling: ', iter_count)
            iter_count +=1
        
        self.actions = actions
        print('actions, ', self.actions)
        self.states = states

    @abstractmethod
    def create_plan_content(self) -> dict:
        ...


class CarOpt(FlatOutputOpt):

    def __init__(self, env_path: str, dt =0.1, yaml_export_path = None, T_guess = 10) -> None:
        super().__init__(env_path, dt = dt, yaml_export_path=yaml_export_path, T_guess=T_guess)
        self.set_car_params()

    
    def set_car_params(self):
        # set geometry as we did in previous assignments
        self.L, self.W, self.H = [3,1.5,1.0]
        self.type = 'car'

    def check_validity_actions(self, actions: np.ndarray) -> bool:
        # define bounds for speed and steering angle
        bounds = {
            's': [-0.5, 2],
            # 'phi': [-np.pi/6, np.pi/6],
        }
        violations = {} # initialize violation dicts

        # extract action columns
        s = actions[:, 0]
        phi = actions[:, 1]
        min_s, max_s = np.min(s), np.max(s)
        min_phi, max_phi = np.min(phi), np.max(phi)
        values = {'s': s, 'phi': phi}

        # check each bound
        for name, (min_b, max_b) in bounds.items():
            arr = values[name]
            violations[f'{name}_below_min'] = np.any(arr < min_b)
            violations[f'{name}_above_max'] = np.any(arr > max_b)

        # store detailed violations for later inspection
        self.bounds_violations = violations

        # overall validity
        actions_valid = not any(violations.values())

        if not actions_valid:
            for key, violated in violations.items():
                if violated:
                    print(f'Bound violation: {key}')
            print(f'Violations detail: {violations}')
            print(f'Action ranges - s: [{min_s}, {max_s}], phi: [{min_phi}, {max_phi}]')

        return actions_valid

    def create_plan_content(self) -> dict:
        # actions_output = list(self.actions) if self.actions is not None else []
        plan_content = {
        'plan': {
            'type': self.type,
            'dt': self.dt,
            'L': self.L,
            'W': self.W,
            'H': self.H,
            'states': [s.tolist() for s in self.states],
            'actions': [a.tolist() for a in self.actions] if self.actions is not None else []
        }
        }
        return plan_content

    @staticmethod
    def compute_states(z, dot_z, ddot_z):
        x = z[:, 0]
        y = z[:, 1]
        dot_x = dot_z[:, 0]
        dot_y = dot_z[:, 1]

        theta = np.arctan2(dot_y, dot_x)
        return np.stack((x, y, theta), axis=1)
    
    def compute_actions(self, z, dot_z, ddot_z):
        dot_x = dot_z[:, 0]
        dot_y = dot_z[:, 1]
        ddot_x = ddot_z[:, 0]
        ddot_y = ddot_z[:, 1]

        s = np.sqrt(dot_x**2 + dot_y**2)
        phi = np.arctan((self.L*(ddot_y*dot_x - dot_y*ddot_x))/((dot_y**2+dot_x**2)**(3/2)))

        return np.stack((s, phi), axis=1)

def main():
    """
    Standalone execution for OptSafe without OMPL.
    This lets you pass a dictionary describing:
        - environment bounds
        - obstacles
        - start, goal
        - geometric path (list of 2D points)
    """

    # ------------------------------------------------------------
    # 1) Minimal demo input for debugging
    # ------------------------------------------------------------
    opt_input = {
        "environment": {
            "min": [0.0, 0.0],
            "max": [10.0, 10.0],
            "obstacles": [
                {"pos": [5.0, 5.0], "size": [2.0, 2.0]},   # square
                {"pos": [3.0, 7.0], "size": [1.0, 2.0]},
            ]
        },
        "motionplanning": {
            "start": [1.0, 1.0, 0.0],
            "goal":  [9.0, 9.0, 0.0],
            "solutionpath": [
                [1.0, 1.0],
                [3.0, 4.0],
                [6.0, 6.0],
                [9.0, 9.0]
            ]
        }
    }

    # ------------------------------------------------------------
    # 2) Run OptSafe using dict instead of YAML
    # ------------------------------------------------------------
    opt = CarOpt(
        env_path=opt_input,   # <-- now a dict, not a filename
        out_path=None,        # no figure output yet
        dt=0.1,
        yaml_export_path=None
    )

    # 3) Run pipeline
    opt.find_hyperplanes()
    opt.create_optimization_vars()
    opt.create_bezier()
    opt.bezier_to_configurations()

    # 4) Show summary results
    print("===== Optimization Done =====")
    print(f"Number of Bezier segments: {len(opt.control_points)}")
    print(f"States shape: {np.array(opt.states).shape}")
    print(f"Actions shape: {np.array(opt.actions).shape}")

    # 5) Optionally plot (if matplotlib installed)
    try:
        opt.create_plot()
    except Exception as e:
        print("Plotting failed:", e)


if __name__ == "__main__":
    main()

    # parser = argparse.ArgumentParser()

    # parser.add_argument("input", help="input file")
    # parser.add_argument("output", help="output file")
    # parser.add_argument("--export-car", default=None, help="exports car plan")
    # parser.add_argument("--export-arm", default=None, help="exports arm plan")
    # args = parser.parse_args()
    

    # if args.export_car:
    #     opt_problem = CarOpt(args.input, args.output, 0.1, args.export_car)

    # elif args.export_arm:
    #     opt_problem = ArmOpt(args.input, args.output, args.export_arm)

    # else:
    #     opt_problem = OptSafeBase(args.input, args.output)

    # opt_problem.find_hyperplanes()
    # opt_problem.create_optimization_vars()
    # opt_problem.create_bezier()
    # opt_problem.create_plot()

    # if args.export_arm or args.export_car:
    #     opt_problem.bezier_to_configurations()
    #     opt_problem.export_to_yaml()
