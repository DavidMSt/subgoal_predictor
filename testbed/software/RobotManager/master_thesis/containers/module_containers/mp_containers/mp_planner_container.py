from dataclasses import dataclass, field
import numpy as np
from collections import OrderedDict

from core.utils.logging_utils import Logger
from master_thesis.containers.base_container import BaseContainer
from master_thesis.containers.module_containers.mp_containers.mp_phase_container import MPPhaseContainer

@dataclass(frozen = False, slots=True)
class AgentMPPlannerState:

    # keep all planned phases
    _phases: OrderedDict[str, MPPhaseContainer] = field(default_factory=OrderedDict)

    # Phase name for motion planning action (None = no planning, string = plan with this phase name)
    _start_planning: str | None = None
    

@dataclass(frozen = True, slots = True)
class AgentMPPlannerConfig:

    # hyperparameters
    # timelimit for each motion planning problem
    timelimit: float = 60.0
    # bias for goal sampling
    goal_bias: float = 0.1
    # size of the goal region
    goal_eps: float = 0.1
    # weight of so2 relative to r2 in distance metric
    so_r2_weight: float = 0.1
    # select which planner to use
    planner: str = 'rrt'
    # Select how to sample
    sampler: str = 'UNIFORM'

    # control bounds (only relevant for kinodynamic case)
    theta_dot_bounds: tuple = (-np.pi/3, np.pi/3)
    v_bounds: tuple = (-1.0, 1.0)

@dataclass(slots = True)
class AgentMPPlannerContainer(BaseContainer):
    state: AgentMPPlannerState = field(default_factory=AgentMPPlannerState)
    config: AgentMPPlannerConfig | None = None
    logger: Logger | None = None

    @property
    def start_planning(self) -> str | None:
        return self.state._start_planning

    @start_planning.setter
    def start_planning(self, value: str | None):
        self.state._start_planning = value

        if self.logger is not None:
            if value is None:
                self.logger.info("Assigned task cleared")
            else:
                self.logger.info(f"Assigned task set to: {value}")

    # prohibit reassignment of the phases dict and make sure input types are correct
    @property
    def phases(self) -> dict[str, MPPhaseContainer]:
        for k, v in self.state._phases.items():
            if not isinstance(k, str):
                raise TypeError("Phase keys must be str")
            if not isinstance(v, MPPhaseContainer):
                raise TypeError("Phase values must be MPPhaseContainer")
        return self.state._phases