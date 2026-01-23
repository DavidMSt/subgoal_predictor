import numpy as np
from matplotlib import pyplot as plt
from numpy.random import normal

from core.utils.control.lib_control.il.ilc import BILBO_STANDARD_REFERENCE_TRAJECTORY, getTransitionMatrixFromSystem, \
    getLearningMatricesOptimal
from core.utils.control.lib_control.il.iml import imlUpdateOptimal, getOptimalLearningMatrix, \
    getOptimalLearningMatrixFromMatrix
from core.utils.control.lib_control.lifted_systems import vec2liftedMatrix, liftedMatrix2Vec
from core.utils.data import generate_time_vector, generate_random_input, resample
from simulation.src.objects.bilbo import BILBO_Dynamics_2D, DEFAULT_BILBO_MODEL, \
    BILBO_Dynamics_2D_Linear, BILBO_2D_POLES, BILBO_MICHAEL_MODEL


def main():
    N = 500
    # Generate the robot
    bilbo_dynamics = BILBO_Dynamics_2D(model=DEFAULT_BILBO_MODEL, Ts=0.01)
    bilbo_dynamics.polePlacement(poles=BILBO_2D_POLES, apply_poles_to_system=True)

    t = np.linspace(0, 5, N)  # 5 seconds over N points
    u = 0.2 * np.sin(2 * np.pi * 0.5 * t)  # 0.2 amplitude, 0.5 Hz frequency

    plt.plot(u)
    plt.show()

    states = bilbo_dynamics.simulate(u)

    theta = [state.theta for state in states]
    v = [state.v for state in states]

    # Add Gaussian noise to theta
    noise_std = 0.005  # Standard deviation of the noise
    noise = normal(0, noise_std, len(theta))
    theta = np.array(theta) + noise

    noise_v_std = 0.005
    noise_v = normal(0, noise_v_std, len(theta))
    v = np.array(v) + noise_v

    plt.plot(theta, label='theta')
    plt.plot(v, label='v')

    plt.legend()
    plt.grid()
    plt.show()


if __name__ == '__main__':
    main()
