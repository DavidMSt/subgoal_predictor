# third party
import math
import time
import copy
import numpy as np
from dataclasses import dataclass, field
import logging

# bilbolab
from applications.FRODO.simulation.frodo_simulation import FRODO_Simulation,  FRODO_ENVIRONMENT_ACTIONS, FRODO_SimulationObject
from extensions.simulation.src.objects.frodo.frodo import FRODO_DynamicAgent
from extensions.simulation.src.core.environment import BASE_ENVIRONMENT_ACTIONS
from extensions.cli.cli import CommandSet, Command, CommandArgument
from extensions.simulation.src.objects.frodo.frodo import FRODO_State
import extensions.simulation.src.core as core
from core.utils.logging_utils import Logger
from master_thesis.general.containers.agent_containers import FRODOAgentContainer, FRODO_Agent_Config
from master_thesis.general.containers.environment_containers import EnvironmentContainer

@dataclass(slots=True)
class LocalWorldRepresentation:
    """
    Local, non-learned representation of what the agent knows.
    """
    # required
    self_agent: FRODOAgentContainer

    # dynamic
    neighbors: dict[str, FRODOAgentContainer] = field(default_factory=dict)

    # static
    env_config: EnvironmentContainer | None = None

    # ---- update interface ----
    def update_self(self):
        pass

    def update_neighbor(self, agent_id: str, container: FRODOAgentContainer):
        self.neighbors[agent_id] = container

    def remove_neighbor(self, agent_id: str):
        self.neighbors.pop(agent_id, None)

    # ---- extraction for RL / GNN ----
    def as_observation(self):
        own = [
            self.self_agent.x,
            self.self_agent.y,
            self.self_agent.psi
        ]

        neigh = []
        for nb in self.neighbors.values():
            neigh.append([nb.x, nb.y, nb.psi])

        limits = self.env_config.limits if self.env_config else None

        return {
            "self": own,
            "neighbors": neigh,
            "limits": limits
        }

@dataclass
class InputPhaseState():
    index: int = 0
    ticks_left: int | None = None

    def reset(self):
        self.index = 0
        self.ticks_left = 0

@dataclass(frozen=True, slots=True)
class InputPhase:
    """Represents executable pre-planned motion phase. 

    Raises:
        ValueError: If the inputs and durations do not match.
        ValueError: If the states do not match the inputs.
    """
    # TODO: Inputs als vorsteuerung -> Zeithorizont verändert sich? (für execution)
    inputs: tuple[np.ndarray, ...] = field(default_factory=tuple)     # shape (2,)
    states: tuple[np.ndarray, ...] | None = field(default=None)  # State objects at segment boundaries
    durations: tuple[float, ...] = field(default_factory=tuple)         # steps per input
    delta_t: float = 0.1 # time increment used during the planned phase (phase time % simulation time != 0 for compatibility reasons)
    phase_state: InputPhaseState = field(default_factory=InputPhaseState)

    def __post_init__(self):
        if len(self.inputs) != len(self.durations):
            raise ValueError("len(inputs) must equal len(durations).")
        if self.states is not None and len(self.states) != len(self.inputs) + 1:
            raise ValueError(f"len(states) must be len(inputs)+1 (or 0 if unknown). States has length: {len(self.states)}, Inputs has length: {len(self.inputs)}.")

class InputPhaseRunner:
    _phases: dict[str, InputPhase] # individual phases that can be executed
    _sim_dt: float # simulation time step
    _active: str # name of the currently active phase
    _current_phase_state: dict[str, int | float]
    _queued_phases: list[str]

    """Holds multiple ExecutionPhase objects; only one is active at a time and executed each step."""
    def __init__(self, simulation_dt: float, logger: Logger | None = None) -> None:
        self._sim_dt = float(simulation_dt)

        # Use logger from agent or create a new one if none provided
        self._logger = logger or logging.getLogger(__name__ + ".PhaseRunner")

        # create base idle phase
        idle_phase = InputPhase(inputs=(np.zeros(2),), durations=(1,), delta_t=self._sim_dt)

        # Register the idle phase
        self._phases: dict[str, InputPhase] = {}
        self.add_phase("idle", idle_phase)

        self._active = 'idle'
        self._pending_end: bool = False
        self._queued_phases = []

    # ---------- Phase management ----------

    def add_phase(self, name: str, phase: InputPhase) -> None:
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
        self._logger.debug(f"Added phase '{name}': {phase}")

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
            self.change_phase(name=name)
        
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

        if name != 'idle':
            self._logger.info(f"Active phase set to '{name}'")

    def change_phase(self, name: str):
        self.active = name

        # not necessary to print ending idle
        if name != 'idle':
            self._logger.info(f"Starting phase '{name}'")

    def get_phase(self, name: str) -> InputPhase:
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
            self._logger.info(f"Phase '{active_phase}' ended, removing it now.")
            del self._phases[active_phase]
        
        if self._queued_phases == []:
            print('no next phases available')
            self.change_phase("idle")
        
        else:
            print('found the next phase')
            phase_name = self._queued_phases.pop()
            self.change_phase(phase_name)


class FRODOGeneralAgent(FRODO_DynamicAgent, FRODO_SimulationObject):
    """
    Lightweight general agent:
    - uses FRODO_DynamicAgent for motion
    - uses FRODO_SimulationObject for world representation
    - optional PhaseRunner for scripted inputs
    """

    def __init__(
    self, 
    agent_id: str,
    Ts=0.1, # TODO: this could probably be removed anyway, since Ts could also be received by env updates? 
    start_config: tuple[float, float, float] = (0.0, 0.0, 0.0),
    color: tuple[float, float, float] = (1.0, 1.0, 1.0)
    ):
        agent_config = FRODO_Agent_Config(color = color, Ts= Ts)

        # ─────────────────────────────────────────────
        # CONTAINER + LOCAL WORLD REPRESENTATION
        # ─────────────────────────────────────────────
        self.container = FRODOAgentContainer(
            agent_id= agent_id,
            config=agent_config,
            state = FRODO_State(x = start_config[0], y = start_config[1], psi = start_config[2], v = 0.0, psi_dot = 0.0)
        )
        self.lwr = LocalWorldRepresentation(self_agent=self.container)
        # ─────────────────────────────────────────────

        self.agent_id = agent_id
        self.color = agent_config.color
        self.size = getattr(agent_config, "size", 0.2)
        self.logger = Logger(agent_id)

        super().__init__(agent_id=agent_id, Ts=Ts)

        self.cli = FRODO_GeneralAgent_CommandSet(self)
        self.runner = InputPhaseRunner(simulation_dt=self.container.Ts, logger=self.logger)
        self.setup_scheduling()

        # Apply initial configuration
        x0, y0, psi0 = start_config
        self.state.x = float(x0)
        self.state.y = float(y0)
        self.state.psi = float(psi0)


    def setup_scheduling(self):
        core.scheduling.Action(action_id=FRODO_ENVIRONMENT_ACTIONS.COMMUNICATION,
                    object=self,
                    function=self.action_frodo_communication,
                    priority=2)

        # Attach input function into scheduling (mirroring VisionAgent behavior)
        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.INPUT].addAction(self._input_function)
        # Attach the update function for the agent containers
        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.OUTPUT].addAction(self._container_update_function)


    def action_frodo_communication(self):
        ...

    # ----------------------------------------------------------------------
    def _input_function(self):
        """
        Custom input logic:
        1. If runner exists → use its control
        2. else → fallback to parent behavior (usually joystick/no-op)
        """
        u = self.runner.step()
        self.input.v = float(u[0])
        self.input.psi_dot = float(u[1])

    # ----------------------------------------------------------------------

    def _container_update_function(self):
        st = self.container.state
        st.x = self.state.x
        st.y = self.state.y
        st.psi = self.state.psi

    # ----------------------------------------------------------------------
    def add_input_phase(
        self,
        name: str,
        inputs: tuple[np.ndarray, ...],
        durations: tuple[int, ...] | None = None,
        delta_t: float = 0.1,
        origin_state=None,
        states: tuple[np.ndarray, ...] = None
    ):
        if durations is None:
            durations = tuple([1] * len(inputs))

        if origin_state is None:
            origin_state = self.state

        # if states == None:
        #     states = self.compute_states(inputs, durations, origin_state, delta_t)
        phase = InputPhase(inputs, states, durations, delta_t)
        self.runner.add_phase(name, phase)

    def _get_state(self):
        return self.state

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

    # ----------------------------------------------------------------------
    def output(self, env):
        """Populate configuration_global for collision detection."""
        # Update the local configuration from the current state
        if hasattr(self, '_configuration') and self._configuration is not None:
            self._configuration['pos'] = [self.state.x, self.state.y]
            if hasattr(self._configuration, 'ori') or 'ori' in dir(self._configuration):
                self._configuration['ori'] = [self.state.psi]

class FRODO_GeneralAgent_CommandSet(CommandSet):
    def __init__(self, agent: FRODOGeneralAgent):
        super().__init__(name=agent.agent_id)
        self.agent = agent

        # ---- Command: set state -----------------------------------------
        cmd_set_state = Command(
            name='set_state',
            description='Set agent pose directly',
            arguments=[
                CommandArgument('x', type=float, optional=True, default=None),
                CommandArgument('y', type=float, optional=True, default=None),
                CommandArgument('psi', type=float, optional=True, default=None),
            ],
            function=self._set_state,
            allow_positionals=True
        )

        # ---- Command: set input -----------------------------------------
        cmd_set_input = Command(
            name='set_input',
            description='Set velocity inputs (v, psi_dot)',
            arguments=[
                CommandArgument('v', type=float),
                CommandArgument('psi_dot', type=float),
            ],
            function=self._set_input,
            allow_positionals=True
        )

        # ---- Command: switch phase --------------------------------------
        cmd_phase = Command(
            name='phase',
            description='Switch to existing phase by name',
            arguments=[
                CommandArgument('name', type=str),
            ],
            function=self._change_phase,
            allow_positionals=True
        )

        self.addCommand(cmd_set_state)
        self.addCommand(cmd_set_input)
        self.addCommand(cmd_phase)

    # ------------------------------------------------------------------
    def _set_state(self, x=None, y=None, psi=None):
        if x is not None:
            self.agent.state.x = x
        if y is not None:
            self.agent.state.y = y
        if psi is not None:
            self.agent.state.psi = psi

    # ------------------------------------------------------------------
    def _set_input(self, v, psi_dot):
        self.agent.input.v = v
        self.agent.input.psi_dot = psi_dot

    # ------------------------------------------------------------------
    def _change_phase(self, name):
        self.agent.activate_phase(name)


def main():
    ...

    while True:
        time.sleep(10)

if __name__ == '__main__':
    
    sim = FRODO_Simulation()
    sim.init()

    cfg = FRODO_Agent_Config(
        color = (1, 0, 0), 
    )

    agent = FRODOGeneralAgent(agent_id = 'frodo01', start_config= [0.0,0.0,0.0])

    # sim.new_agent(agent_id='vfrodo1', fov_deg=100, vision_radius=1.5)
    sim.add_agent(agent)

    sim.start()

    while True:
        time.sleep(10)