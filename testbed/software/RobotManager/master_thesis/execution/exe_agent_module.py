# 3rd party
import numpy as np
from typing import Type
from dataclasses import dataclass, field
import math

# bilbolab
from core.utils.logging_utils import Logger

# master thesis
from master_thesis.containers.general_containers.agent_container import FRODOAgentContainer
from master_thesis.containers.module_containers.exe_containers.exe_container import ExecutionContainer
from master_thesis.containers.module_containers.mp_containers.mp_phase_container import MPPhaseContainer, MPPhaseConfig
# TODO: Apply offset bidirectional from ompl to simulation and from simulation back (initialization of start config)

class InputPhaseRunner:
    _phases: dict[str, MPPhaseContainer] # individual phases that can be executed
    _sim_dt: float # simulation time step
    _active: str # name of the currently active phase
    _current_phase_state: dict[str, int | float]
    _queued_phases: list[str]

    """Holds multiple ExecutionPhase objects; only one is active at a time and executed each step."""
    def __init__(self, simulation_dt: float, logger: Logger) -> None:
        self._sim_dt = float(simulation_dt)

        # Use logger from agent or create a new one if none provided
        self.logger = logger

        # create base idle phase
        config = MPPhaseConfig(inputs=(np.zeros(2),), durations=(1,), delta_t=self._sim_dt)
        idle_phase = MPPhaseContainer(config)

        # Register the idle phase
        self._phases: dict[str, MPPhaseContainer] = {}
        self.add_phase("idle", idle_phase)

        self._active = 'idle'
        self._pending_end: bool = False
        self._queued_phases = []

    # ---------- Phase management ----------

    def add_phase(self, name: str, phase: MPPhaseContainer) -> None:
        # Check 
        if name in self._phases:
            raise ValueError(f"Phase '{name}' already exists with a different object.")
        ratio = phase.delta_t / self._sim_dt
        if not math.isclose(ratio, round(ratio), rel_tol=0.0, abs_tol=1e-12):
            raise ValueError(
                f"Incompatible phase delta_t: {phase.delta_t}, simulation dt: {self._sim_dt}. "
                f"Expected an integer multiple; got ratio={ratio}"
            )
        self._phases[name] = phase
        self.logger.debug(f"Added phase '{name}': {phase}")

    def activate_phase(self, name: str, *, cut_current: bool = False, reset: bool = True) -> None:
        if name not in self._phases:
            raise KeyError(f"Unknown phase '{name}', can't be activated. Add it to the runner first.")
        if reset:
            p = self._phases[name]
            p.phase_state.index = 0
            p.phase_state.ticks_left = None # will be set on first step when active 

        # Clear any pending end carried over from a previous phase
        self._pending_end = False # TODO: remove this param

        # immediately stop current phase and start the next one
        if cut_current or self.active == 'idle': 
            self.active =name
        
        # wait until it is finished, just add new phase to active queue
        else:
            self._queued_phases.append(name)

    @property
    def active(self) -> str:
        return self._active

    @active.setter
    def active(self, name: str) -> None:
        if name not in self._phases:
            raise KeyError(f"Unknown phase '{name}', can't be set as active. Add it to the runner first.")
        self._active = name

        # if name != 'idle':
        self.logger.info(f"Active phase set to '{name}'")

    def get_phase(self, name: str) -> MPPhaseContainer:
        return self._phases[name]

    # ---------- Stepping ----------
    def step(self) -> np.ndarray:
        """Advance the active phase by one simulation tick. Returns control or None when finished."""

        # If a phase ended on the previous tick, finalize the switch now
        if getattr(self, "_pending_end", False):
            self._pending_end = False
            self.phase_ended()

        phase = self._phases[self.active]
        ticks_left = phase.phase_state.ticks_left
        index = phase.phase_state.index

        if ticks_left is None or ticks_left == 0:
            r = phase.delta_t / self._sim_dt
            r_int = round(r)  # assert isclose(r, r_int)
            ticks_left = max(1, math.ceil(phase.durations[index] * r_int))

        u = phase.inputs[index]

        ticks_left -= 1
        if ticks_left == 0:
            index += 1
            if index >= len(phase.inputs):
                if self.active != 'idle':
                    # Defer switching to idle until the next call, so that external logging
                    # sees the phase that produced this tick's control `u`.
                    self._pending_end = True
                else:
                    # Idle should be infinite: wrap its index and keep producing zeros
                    phase.phase_state.index = 0
                phase.phase_state.ticks_left = 0
                return u
            phase.phase_state.index = index

        phase.phase_state.ticks_left = ticks_left
        return u

    def phase_ended(self):
        active_phase = self.active
        if active_phase != "idle": # no need to tell every time the idle phase ends
            del self._phases[active_phase]
        
        if self._queued_phases == []:
            # no next phases activated
            self.active = "idle"
        
        else:
            phase_name = self._queued_phases.pop()
            self.active = phase_name

        self.logger.info(f"Phase '{active_phase}' ended, now transitioning to phase: {self.active}")

    

class EXEAgentModule():
    exe_cont: ExecutionContainer

    def __init__(self, agent_cont: FRODOAgentContainer, Ts: float, logger: Logger) -> None:
        self.agent_cont = agent_cont
        self.logger = logger
        self.exe_cont = ExecutionContainer()
        self.runner = InputPhaseRunner(simulation_dt=Ts, logger=self.logger)

    # ----------------------------------------------------------------------
    def add_planned_phase(
        self,
        name: str,
        inputs: tuple[np.ndarray, ...],
        durations: tuple[int, ...] | None = None,
        delta_t: float = 0.1,
        origin_state=None,
        states: tuple[np.ndarray, ...] | None = None
    ):
        """
        - Register a pre-planned input phase to the agent
        - Note: The phase timesteps are then translated into simulation timestep

        Args:
            name (str): Name the phase will be registered under
            inputs (tuple[np.ndarray, ...]): series of inputs, one for each PHASE timestep
            durations (tuple[int, ...] | None, optional): Scalar describing the number of PHASE timesteps an input has Defaults to None.
            delta_t (float, optional): Delta t used in this phase, together with durations this gets translated into simulation time steps. Defaults to 0.1.
            origin_state (_type_, optional): Describe from which state this should be executed. Defaults to None.
            states (tuple[np.ndarray, ...], optional): Sequence of states the agent should follow according to planning. Defaults to None.
        """
        if durations is None:
            durations = tuple([1] * len(inputs))

        if origin_state is None:
            origin_state = self.agent_cont.state

        config = MPPhaseConfig(
            inputs = inputs,
            states= states,
            durations= durations,
            delta_t= delta_t
        )
        
        in_cont = MPPhaseContainer(config = config)

        self.runner.add_phase(name, in_cont)


    # ----------------------------------------------------------------------
    # def compute_states(self, inputs, durations, initial_state, delta_t):
    #     ratio = delta_t / self.Ts
    #     r_int = round(ratio)
    #     if not math.isclose(ratio, r_int, abs_tol=1e-12):
    #         raise ValueError(f"delta_t {delta_t} not integer multiple of Ts {self.Ts}")

    #     x = copy.deepcopy(initial_state)
    #     states = [copy.deepcopy(x)]

    #     for duration, u_arr in zip(durations, inputs):
    #         sim_ticks = duration * r_int

    #         u = self.input_space.getState()
    #         u["v"] = float(u_arr[0])
    #         u["psi_dot"] = float(u_arr[1])

    #         for _ in range(sim_ticks):
    #             x = self.dynamics._dynamics(state=x, input=u)

    #         states.append(copy.deepcopy(x))

    #     return tuple(states)

    # ----------------------------------------------------------------------
    def activate_phase(self, name: str, reset: bool = True):
        self.runner.activate_phase(name, reset = reset)
