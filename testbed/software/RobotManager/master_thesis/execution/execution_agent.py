from typing import Type, TypeVar, overload, cast
import numpy as np

from master_thesis.general.general_agent import FRODOGeneralAgent
from general.general_simulation import FRODO_general_Simulation, FrodoGeneralEnvironment
from applications.FRODO.simulation.frodo_simulation import FRODO_Simulation, FRODO_ENVIRONMENT_ACTIONS
from applications.FRODO.simulation.frodo_simulation import FrodoEnvironment

class ExecutionAgent(FRODOGeneralAgent):
    def __init__(self, start_config: list[float], fov_deg=360, view_range=1.5, runner: bool = True, *args, **kwargs) -> None:
        super().__init__(start_config, fov_deg, view_range, runner, *args, **kwargs)


if __name__ == "__main__":
    sim = FRODO_general_Simulation(Ts = 0.1, use_web_interface = True, env = FrodoGeneralEnvironment)
    sim.init()
    sim.start()

    # Add agents
    test_agent_a = sim.add_agent("test_agent_a", agent_class= FRODOGeneralAgent, start_config = [-1.0, 0.0, 0.0], dt = sim.environment.Ts)
    test_agent_b = sim.add_agent("test_agent_b", agent_class= FRODOGeneralAgent, start_config = [1.0, 0.0, np.pi], dt = sim.environment.Ts)

    # create test_input phase
    inputs = [np.array([.2, 0.0]) for _ in range(40)]
    durations = [1] * len(inputs)


    # pick different delta t -> one step for phase now equals 4 steps in the simulation
    test_agent_a.add_input_phase('test_phase', inputs = inputs, durations= durations, delta_t=0.4, compute_states = True)
    test_agent_a.change_phase('test_phase', reset= True)

    test_agent_b.add_input_phase('test_phase', inputs = inputs, durations= durations, delta_t=0.4, compute_states = True)
    test_agent_b.change_phase('test_phase', reset= True)
