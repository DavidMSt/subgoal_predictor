from matplotlib import pyplot as plt
import numpy as np

from core.utils.data import generate_time_vector_by_length
from core.utils.files import get_absolute_path
from core.utils.json_utils import readJSON
from core.utils.plotting.plot import quick_plot

if __name__ == '__main__':
    data = readJSON(get_absolute_path('./step_20260116_111954.json'))


    theta = [sample['lowlevel']['estimation']['state']['theta'] for sample in data['samples']]
    v = [sample['lowlevel']['estimation']['state']['v'] for sample in data['samples']]
    theta_dot = [sample['lowlevel']['estimation']['state']['theta_dot'] for sample in data['samples']]
    u = [sample['lowlevel']['control']['input_ext']['u_left'] + sample['lowlevel']['control']['input_ext']['u_right'] for sample in data['samples']]

    dt = 0.01
    s = np.cumsum(v) * dt

    t = generate_time_vector_by_length(start=0, num_samples=len(theta), dt=dt)

    quick_plot(t, [theta, v, theta_dot, s], labels=['Theta', 'v', 'Theta dot', 's'])


    quick_plot(t, v)
    quick_plot(t, theta)