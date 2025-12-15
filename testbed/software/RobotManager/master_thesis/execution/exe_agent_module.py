# 3rd party
import numpy as np
from typing import Type
from collections import OrderedDict
import math

# bilbolab
from core.utils.logging_utils import Logger

# master thesis
from master_thesis.containers.general_containers.agent_container import FRODOAgentContainer
from master_thesis.containers.module_containers.exe_containers.exe_container import AgentExeContainer
from master_thesis.containers.module_containers.mp_containers.mp_phase_container import MPPhaseContainer, MPPhaseConfig, MPPhaseState

class EXEAgentModule:
    """Manages execution of motion phases."""

    def __init__(self, agent_cont: FRODOAgentContainer, logger: Logger):
        self.agent_cont = agent_cont
        self.simulation_dt = agent_cont.Ts
        self.logger = logger
        self.logger.info(f"EXE module initialized with simulation_dt={self.simulation_dt}")

        # Execution container for high-level state
        self.exe_cont = AgentExeContainer()

        # Phase registry (same as MP module pattern)
        self._phases: OrderedDict[str, MPPhaseContainer] = OrderedDict()

        # Execution state
        self._active_phase: str = 'idle'
        self._pending_end: bool = False
        self._queued_phases: list[str] = []

        # Create and register idle phase
        self._create_idle_phase()
    
    def add_phase(self, name: str, phase: MPPhaseContainer) -> None:
        """Add phase to execution registry."""
        if name in self._phases:
            raise ValueError(f"Phase '{name}' already exists")

        # Validate dt compatibility
        self._validate_dt_compatibility(phase.config.delta_t)

        self._phases[name] = phase
        self.logger.debug(f"Added phase '{name}'")
    
    def activate_phase(self, name: str, *, cut_current: bool = False, reset: bool = True):
        """Activate a phase for execution."""
        if name not in self._phases:
            raise KeyError(f"Unknown phase '{name}'")

        self.logger.info(f"activate_phase called: name={name}, current_active={self._active_phase}, pending_end={self._pending_end}, reset={reset}")

        if reset:
            self._phases[name].state.reset()

        self._pending_end = False

        if cut_current or self._active_phase == 'idle':
            self._active_phase = name
            self.exe_cont.state.execution_mode = 'phase'
            self.logger.info(f"Active phase set to '{name}', mode={self.exe_cont.state.execution_mode}")
        else:
            self._queued_phases.append(name)
            self.logger.info(f"Phase '{name}' queued for execution")

    def step(self) -> np.ndarray:
        """Execute pre-planned phase mode."""
        if self._active_phase != 'idle':
            self.logger.info(f"step() called: active_phase={self._active_phase}, index={self._phases[self._active_phase].state.index}, pending_end={self._pending_end}, mode={self.exe_cont.state.execution_mode}")

        # Handle phase transitions
        if self._pending_end:
            self._pending_end = False
            self._transition_phase()

        phase = self._phases[self._active_phase]

        # Get current control from phase container
        u = self._step_phase(phase)

        return u
    
    def _step_phase(self, phase: MPPhaseContainer) -> np.ndarray:
        """Step through a single phase using its state."""
        state = phase.state
        config = phase.config

        assert isinstance(config, MPPhaseConfig)
        
        # Initialize ticks if needed
        if state.ticks_left is None or state.ticks_left == 0:
            # durations are in seconds, convert to simulation ticks
            duration_in_seconds = config.durations[state.index]
            state.ticks_left = max(1, math.ceil(duration_in_seconds / self.simulation_dt))
            if self._active_phase != 'idle':
                self.logger.info(f'Input {state.index}: duration={duration_in_seconds}s, sim_dt={self.simulation_dt}, ticks_left={state.ticks_left}, total_inputs={len(config.inputs)}')
        
        u = config.inputs[state.index]
        
        # Advance state
        state.ticks_left -= 1
        if state.ticks_left == 0:
            state.index += 1
            if state.index >= len(config.inputs):
                if self._active_phase != 'idle':
                    self._pending_end = True
                else:
                    state.index = 0  # Idle loops forever
                state.ticks_left = 0
                return u

        return u

    def _transition_phase(self):
        """Handle phase transition when current phase ends."""
        active_phase_name = self._active_phase

        # Track completed phase
        if active_phase_name != 'idle':
            self.exe_cont.state.completed_phases.append(active_phase_name)
            self.exe_cont.state.total_phases_executed += 1

            # Remove phase if configured
            if self.exe_cont.config.auto_remove_completed:
                del self._phases[active_phase_name]

        # Activate next queued phase or go to idle
        if self._queued_phases:
            next_phase = self._queued_phases.pop(0)
            self._active_phase = next_phase
            self.logger.info(f"Phase '{active_phase_name}' ended ({self.agent_cont.state}), transitioning to '{next_phase}'")
        else:
            # Set to idle phase
            self._active_phase = 'idle'

            self.exe_cont.state.execution_mode = 'idle'

            # reset flag, to keep agent from immediately starting again
            self.exe_cont.start_execution = False
            self.logger.info(f"Phase '{active_phase_name}' ended ({self.agent_cont.state}), transitioning to idle")

    def _create_idle_phase(self):
        """Create the default idle phase (zero inputs)."""
        idle_config = MPPhaseConfig(
            inputs=[np.zeros(2)],
            durations=[1.0],
            delta_t=self.simulation_dt,
            states=[np.zeros(3), np.zeros(3)],  # Start and end state (x, y, psi)
            success=True
        )
        idle_phase = MPPhaseContainer(
            config=idle_config,
            state=MPPhaseState()
        )
        self._phases['idle'] = idle_phase

    def _validate_dt_compatibility(self, phase_delta_t: float):
        """Validate that phase delta_t is compatible with simulation dt."""
        ratio = phase_delta_t / self.simulation_dt
        ratio_int = round(ratio)

        if not math.isclose(ratio, ratio_int, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError(
                f"Incompatible phase delta_t: {phase_delta_t}, simulation dt: {self.simulation_dt}. "
                f"Expected an integer multiple; got ratio={ratio}"
            )

    @property
    def active_phase(self) -> str:
        """Get the name of the currently active phase."""
        return self._active_phase

    @property
    def phases(self) -> dict[str, MPPhaseContainer]:
        """Get read-only access to registered phases."""
        return self._phases
