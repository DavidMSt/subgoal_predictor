import cvxpy as cp
import numpy as np

try:
    import matplotlib
    matplotlib.use('Agg')                      # headless backend
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


def bezier_curve(t, control_points):
    basis = np.array([1, t, t**2, t**3])
    coeffs = np.array([[1, 0, 0, 0], [-3, 3, 0, 0], [3, -6, 3, 0], [-1, 3, -3, 1]])
    return basis @ coeffs @ np.array(control_points)

# define the bezier length that we want to optimize later
def eval_bezier_length(control_points):
    t_vals = np.linspace(0, 1, 100)
    points = cp.vstack([bezier_curve(t, control_points) for t in t_vals])
    lengths = cp.norm(cp.diff(points, axis=0), axis=1)
    return cp.sum(lengths)

def main():

    # Define start, goal, and control regions -> this tells us where splines should be 
    q_start, q_goal = np.array([0.5, 2.5]), np.array([9.5, 0.5])
    free_regions = [
        (np.array([0, 2]), np.array([6, 3])),  # Region for p
        (np.array([4, 1]), np.array([6, 5])),  # Region for q
        (np.array([4, 0]), np.array([10, 1]))  # Region for r
    ]

    # number of the bezier points
    bezier_points = 4

    # Define control points as optimization variables
    p = [cp.Variable(2) for _ in range(bezier_points)]
    q = [cp.Variable(2) for _ in range(bezier_points)]
    r = [cp.Variable(2) for _ in range(bezier_points)]

    # Define constraints for control points within allowed regions
    constraints = [
        p[0] == q_start,
        p[3] >= [4, 2], p[3] <= [6, 3],
        q[0] == p[3], q[3] >= [4, 0], q[3] <= [6, 1],
        r[0] == q[3], r[3] == q_goal
    ]

    # Add region constraints for p, q, and r control points
    for (c_low, c_high), points in zip(free_regions, [p[1:3], q[1:3], r[1:3]]):
        for point in points:
            constraints += [c_low <= point, point <= c_high]

    # Add continuity and smoothness constraints
    constraints += [
        p[2] - p[3] == q[0] - q[1], p[1] - 2 * p[2] + p[3] == q[0] - 2 * q[1] + q[2],
        q[2] - q[3] == r[0] - r[1], q[1] - 2 * q[2] + q[3] == r[0] - 2 * r[1] + r[2]
    ]

    # Calculate the approximate length of each of the three b-splines
    length_p = eval_bezier_length(p)
    length_q = eval_bezier_length(q)
    length_r = eval_bezier_length(r)

    # Objective function to minimize the total length of the spline
    objective = cp.Minimize(length_p + length_q + length_r)

    # Solve the optimization problem
    prob = cp.Problem(objective, constraints)
    prob.solve(verbose=True)

    # Extract optimized control points values
    p_vals = np.array([var.value for var in p])
    q_vals = np.array([var.value for var in q])
    r_vals = np.array([var.value for var in r])

    # Generate points on the Bezier curves
    t_vals = np.linspace(0, 1, 100)
    curve_p = np.array([bezier_curve(t, p_vals) for t in t_vals])
    curve_q = np.array([bezier_curve(t, q_vals) for t in t_vals])
    curve_r = np.array([bezier_curve(t, r_vals) for t in t_vals])

    if not HAS_MATPLOTLIB:
        print("…skipping PDF generation…")
        return

    else:

        # Plotting the curves and allowed regions
        fig, ax = plt.subplots()
        ax.plot(curve_p[:, 0], curve_p[:, 1], label='Curve P')
        ax.plot(curve_q[:, 0], curve_q[:, 1], label='Curve Q')
        ax.plot(curve_r[:, 0], curve_r[:, 1], label='Curve R')

        # Add region patches
        for (c_low, c_high) in free_regions:
            ax.add_patch(patches.Rectangle(c_low, *(c_high - c_low), edgecolor='r', facecolor='none', linestyle='--'))

        # Configure and save the plot
        ax.set_xlim([0, 10])
        ax.set_ylim([0, 5])
        ax.legend()
        fig.savefig('opt_toy.pdf')
        # plt.show()
       

    print(f"Optimized control points for P: {p_vals}")

if __name__ == '__main__':
    main()
