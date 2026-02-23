from dataclasses import dataclass, field
import numpy as np

from master_thesis.containers.base_container import BaseContainer

@dataclass(frozen=False, slots=True)
class MPPhaseState:
    """Mutable runtime state for phase execution tracking."""
    index: int = 0
    ticks_left: int | None = None

    def reset(self):
        self.index = 0
        self.ticks_left = None

@dataclass(frozen=True, slots=True)
class MPPhaseConfig:
    """Immutable configuration for a pre-planned motion phase.

    Raises:
        ValueError: If the inputs and durations do not match.
        ValueError: If the states do not match the inputs.
    """
    # Required execution data - must be provided
    inputs: list[np.ndarray]  # Control inputs, shape (2,) each
    durations: list[float]  # Duration per input
    delta_t: float  # Time increment used during planning
    states: list[np.ndarray]  # State objects at segment boundaries

    # Planning problem metadata (optional)
    start: np.ndarray | None = None
    goal: np.ndarray | None = None
    success: bool = False

    # Optional: raw states for debugging/visualization
    raw_states: list[np.ndarray] | None = None

    # Timing / metrics (optional)
    computation_time: float | None = None
    path_length: float | None = None
    cost: float | None = None

    def __post_init__(self):
        # Validate required execution data
        if len(self.inputs) != len(self.durations):
            raise ValueError(
                f"len(inputs) must equal len(durations). "
                f"Got inputs={len(self.inputs)}, durations={len(self.durations)}"
            )

        if len(self.states) != len(self.inputs) + 1:
            raise ValueError(
                f"len(states) must be len(inputs)+1. "
                f"Got states={len(self.states)}, inputs={len(self.inputs)}"
            )

@dataclass(frozen=False, slots=False)
class MPPhaseContainer(BaseContainer):
    """Container for executable pre-planned motion phase."""
    config: MPPhaseConfig = field(default_factory=MPPhaseConfig)
    state: MPPhaseState = field(default_factory=MPPhaseState)
