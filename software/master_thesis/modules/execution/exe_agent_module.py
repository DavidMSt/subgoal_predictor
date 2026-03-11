# 3rd party
import numpy as np
from typing import Type
from collections import OrderedDict
import math

# bilbolab
from core.utils.logging_utils import Logger

# master thesis
from master_thesis.containers.general_containers.frodo_agent_container import FRODOAgentContainer
from master_thesis.containers.module_containers.exe_containers.exe_container import AgentExeContainer
from master_thesis.containers.module_containers.mp_containers.mp_phase_container import MPPhaseContainer, MPPhaseConfig, MPPhaseState

class EXEAgentModule:
    """Manages execution of motion phases."""

    def __init__(self, agent_cont: FRODOAgentContainer, logger: Logger,
                 tracking_gain: float = 1.0):
        self.agent_cont = agent_cont
        self.simulation_dt = agent_cont.Ts
        self.tracking_gain = tracking_gain
        self._v_min = 0.05  # m/s — minimum speed denominator in Stanley controller
        self.logger = logger
        self.logger.info(f"EXE module initialized with simulation_dt={self.simulation_dt}")

        # Execution container for high-level state
        self.exe_cont = AgentExeContainer()

        # Phase registry (same as MP module pattern)
        self._phases: OrderedDict[str, MPPhaseContainer] = OrderedDict()

        # Transient flag for within-tick phase transitions
        self._pending_end: bool = False

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

        self.logger.info(f"activate_phase called: name={name}, current_active={self.exe_cont.state.active_phase}, pending_end={self._pending_end}, reset={reset}")

        if reset:
            self._phases[name].state.reset()

        self._pending_end = False

        if cut_current or self.exe_cont.state.active_phase == 'idle':
            self.exe_cont.state.active_phase = name
            self.exe_cont.state.execution_mode = 'phase'
            self.logger.info(f"Active phase set to '{name}', mode={self.exe_cont.state.execution_mode}")
        else:
            self.exe_cont.state.queued_phases.append(name)
            self.logger.info(f"Phase '{name}' queued for execution")

    def step(self) -> np.ndarray:
        """Execute pre-planned phase mode."""

        # Handle phase transitions
        if self._pending_end:
            self._pending_end = False
            self._transition_phase()

        phase = self._phases[self.exe_cont.state.active_phase]

        # Get current control from phase container
        u = self._step_phase(phase)

        return u
    
    def _path_controller(self, u_ff: np.ndarray, ref_state: np.ndarray) -> np.ndarray:
        """Stanley path tracking controller.

        Combines heading error and cross-track error into a single ψ̇ correction
        on top of the feedforward input.

        Args:
            u_ff:      feedforward input [v, ψ̇]
            ref_state: reference state   [x_ref, y_ref, ψ_ref]
        """
        x_ref, y_ref, psi_ref = ref_state
        v = max(float(self.agent_cont.v), self._v_min)

        # Heading error — wrap to [-π, π]
        psi_err = psi_ref - self.agent_cont.psi
        psi_err = (psi_err + np.pi) % (2 * np.pi) - np.pi

        # Cross-track error: positive when robot is to the RIGHT of the path
        # (needs left / positive ψ̇ correction)
        dx = self.agent_cont.x - x_ref
        dy = self.agent_cont.y - y_ref
        e_ct = dx * np.sin(psi_ref) - dy * np.cos(psi_ref)

        # Stanley correction
        psi_dot_correction = psi_err + np.arctan2(self.tracking_gain * e_ct, v)

        # Scale velocity down with cross-track error: large deviation → slow down.
        # Factor halves speed at ~0.15 m cross-track error.
        v_scale = 1.0 / (1.0 + 5.0 * e_ct ** 2)
        v_cmd = u_ff[0] * v_scale

        return np.array([v_cmd, u_ff[1] + psi_dot_correction])

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
            
        u = self._path_controller(
            u_ff=config.inputs[state.index],
            ref_state=config.states[state.index],
        )
        
        # Advance state
        state.ticks_left -= 1
        if state.ticks_left == 0:
            state.index += 1
            if state.index >= len(config.inputs):
                if self.exe_cont.state.active_phase != 'idle':
                    self._pending_end = True
                else:
                    state.index = 0  # Idle loops forever
                state.ticks_left = 0
                return u

        return u

    def _transition_phase(self):
        """Handle phase transition when current phase ends."""
        active_phase_name = self.exe_cont.state.active_phase

        # Track completed phase
        if active_phase_name != 'idle':
            self.exe_cont.state.completed_phases.append(active_phase_name)
            self.exe_cont.state.total_phases_executed += 1

            # Remove phase if configured
            if self.exe_cont.config.auto_remove_completed:
                del self._phases[active_phase_name]

        # Activate next queued phase or go to idle
        if self.exe_cont.state.queued_phases:
            next_phase = self.exe_cont.state.queued_phases.pop(0)
            self.exe_cont.state.active_phase = next_phase
            self.logger.info(f"Phase '{active_phase_name}' ended ({self.agent_cont.state}), transitioning to '{next_phase}'")
        else:
            # Set to idle phase
            self.exe_cont.state.active_phase = 'idle'

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
        return self.exe_cont.state.active_phase

    @property
    def phases(self) -> dict[str, MPPhaseContainer]:
        """Get read-only access to registered phases."""
        return self._phases
