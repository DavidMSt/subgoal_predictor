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
    inputs: tuple[np.ndarray, ...] = field(default_factory=tuple)      # shape (2,) each
    states: tuple[np.ndarray, ...] | None = field(default=None)        # State objects at segment boundaries
    durations: tuple[float, ...] = field(default_factory=tuple)        # duration per input
    delta_t: float = 0.1  # time increment used during the planned phase

    def __post_init__(self):
        if len(self.inputs) != len(self.durations):
            raise ValueError("len(inputs) must equal len(durations).")
        if self.states is not None and len(self.states) != len(self.inputs) + 1:
            raise ValueError(
                f"len(states) must be len(inputs)+1 (or None if unknown). "
                f"States has length: {len(self.states)}, Inputs has length: {len(self.inputs)}."
            )

@dataclass(frozen=False, slots=False)
class MPPhaseContainer(BaseContainer):
    """Container for executable pre-planned motion phase."""
    config: MPPhaseConfig = field(default_factory=MPPhaseConfig)
    state: MPPhaseState = field(default_factory=MPPhaseState)
