import time

import matplotlib.pyplot as plt
import numpy as np

from extensions.simulation.src.core.environment import BASE_ENVIRONMENT_ACTIONS
from extensions.simulation._archive.bilbo import BILBO_DynamicAgent, DEFAULT_BILBO_MODEL
from extensions.simulation.src.objects.base_environment import BaseEnvironment
from extensions.babylon.src.babylon import BabylonVisualization
# from extensions.babylon.archive.objects.objects import BILBO, Floor
from core.utils.keyboard import ArrowKeys


class TestAgent(BILBO_DynamicAgent):

    def __init__(self, agent_id, *args, **kwargs):
        super().__init__(agent_id, *args, **kwargs)

        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.INPUT].addAction(self.input_function)
        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.OUTPUT].addAction(self.output_function)

        self.keys = ArrowKeys()

    def init(self):
        ...

    def input_function(self):
        ...
        forward = -2 * (self.keys.keys['UP'] - self.keys.keys['DOWN'])
        turn = -1 * (self.keys.keys['LEFT'] - self.keys.keys['RIGHT'])
        self.input = [forward + turn, forward - turn]

    def output_function(self):
        self.output = self.state


def main():
    env = BaseEnvironment(Ts=0.02, run_mode='rt')

    bilbo1 = TestAgent(agent_id='bilbo1')
    env.addObject(bilbo1)

    env.initialize()
    env.start(thread=True)

    while True:
        # print("XXX")
        print(bilbo1.configuration)
        time.sleep(1)


def test_babylon():
    babylon = BabylonVisualization(show='chromium')
    babylon.init()

    bilbo1_object = BILBO("bilbo1", color=[1, 0, 0.5])
    floor_object = Floor("floor1", tile_size=0.5, tiles_x=10, tiles_y=10)
    babylon.addObject(bilbo1_object)
    babylon.addObject(floor_object)

    babylon.start()

    while True:
        time.sleep(1)


def example_only_bilbo():
    bilbo1 = BILBO_DynamicAgent(agent_id='bilbo1', model=DEFAULT_BILBO_MODEL)

    input = 0.2*np.ones((250, 2), dtype=float)
    output = bilbo1.simulate(input)

    theta = [state['theta'].value for state in output]

    plt.plot(theta)
    plt.show()


def test_together():
    env = BaseEnvironment(Ts=0.01, run_mode='rt')
    K = np.asarray([[0, 0, -0.12, -0.24, -0.04, 0, -0.01],
                    [0, 0, -0.12, -0.24, -0.04, 0, 0.01]])

    # K = np.asarray([[0, 0, -0.55471499, -1.02264007, -0.19804071, 0., -0.16756627],
    #                 [0., 0., -0.55471499, -1.02264007, -0.19804071, 0., 0.16756627]])

    # K = K/10
    bilbo1 = TestAgent(agent_id='bilbo1', model=DEFAULT_BILBO_MODEL)
    env.addObject(bilbo1)

    babylon = BabylonVisualization(show='chromium')
    bilbo1_object = BILBO("bilbo1", color=[0, 1, 0], text='1')
    bilbo2_object = BILBO("bilbo2", color=[0, 0, 1], text='B2')
    floor_object = Floor("floor1", tile_size=0.5, tiles_x=10, tiles_y=10)
    babylon.addObject(bilbo1_object)
    babylon.addObject(bilbo2_object)
    babylon.addObject(floor_object)

    env.initialize()
    env.start(thread=True)
    babylon.start()

    while True:
        bilbo1_object.setConfiguration(x=float(bilbo1.configuration['pos']['x']),
                                       y=float(bilbo1.configuration['pos']['y']),
                                       theta=float(bilbo1.configuration['theta'].value),
                                       psi=float(bilbo1.configuration['psi'].value))

        bilbo2_object.setConfiguration(x=0,
                                       y=0,
                                       theta=0,
                                       psi=0)

        time.sleep(0.04)


if __name__ == '__main__':
    example_only_bilbo()
