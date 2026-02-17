from dataclasses import dataclass, field
import numpy as np
from master_thesis.containers.base_container import BaseContainer

@dataclass(frozen=False, slots=False)
class AgentExecutionState:
    """High-level execution state for the agent."""
    start_execution: bool = False

    # Waypoint tracking (stub for future - simple execution without full phases)
    waypoints: list[tuple[float, float]] | None = None
    current_waypoint_idx: int = 0

    # Phase tracking
    active_phase: str = 'idle'
    queued_phases: list[str] = field(default_factory=list)
    pending_phase: str | None = None  # staged but not yet activated

    # Phase history/management
    completed_phases: list[str] = field(default_factory=list)  # Track what's been executed
    stopped_phases: list[str] = field(default_factory=list)    # Track interrupted phases

    # Execution mode: 'idle', 'phase', 'waypoint'
    execution_mode: str = 'idle'

    # Statistics
    total_phases_executed: int = 0
    last_phase_end_time: float | None = None

@dataclass(frozen=True, slots=True)
class ExecutionConfig:
    """Execution parameters."""

    # Phase execution behavior
    auto_remove_completed: bool = True  # Remove phases after completion
    allow_phase_interruption: bool = True

    # Waypoint execution settings (stub for future)
    waypoint_tolerance_xy: float = 0.15
    waypoint_approach_speed: float = 0.5

@dataclass(frozen=False, slots=False)
class AgentExeContainer(BaseContainer):
    """Container for agent execution state and configuration."""
    config: ExecutionConfig = field(default_factory=ExecutionConfig)
    state: AgentExecutionState = field(default_factory=AgentExecutionState)
