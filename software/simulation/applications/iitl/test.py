from matplotlib import pyplot as plt

from extensions.simulation.applications.iitl.bilbo_iitl import generate_learning_set
from extensions.simulation._archive.bilbo import BILBO_DynamicAgent
from extensions.simulation.utils.data import fun_sample_random_input, generate_time_vector


def input_generation():
    t_vector = generate_time_vector(0, 10, 0.1)
    print(t_vector)
    f_cutoff = 1  # cutoff frequency in Hz
    sigma_I = 1  # amplitude scaling

    plt.figure(figsize=(10, 6))
    for i in range(10):
        u = fun_sample_random_input(t_vector, f_cutoff, sigma_I)
        plt.plot(t_vector, u, label=f'Input {i + 1}')

    plt.xlabel('Time (s)')
    plt.ylabel('Amplitude')
    plt.title('Random Input Trajectories')
    plt.legend()
    plt.grid(True)
    plt.show()


def generation_of_learning_set():
    agent = BILBO_DynamicAgent(agent_id='source')

    data = generate_learning_set(agent, 10, 1000, 0.01)
    print(data)


if __name__ == '__main__':
    generation_of_learning_set()
