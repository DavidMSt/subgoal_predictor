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
    # weight of so2 relative to r2 in distance metric (0.0 = xy-only goal, psi ignored)
    so_r2_weight: float = 0.0
    # select which planner to use for replanning (initial plan always uses PRM*)
    planner: str = 'rrt-connect'
    # time budget [s] for building the PRM* roadmap (once per environment)
    roadmap_time: float = 30.0
    # Select how to sample
    sampler: str = 'UNIFORM'

    # control bounds (only relevant for kinodynamic case)
    theta_dot_bounds: tuple = (-np.pi/3, np.pi/3)
    v_bounds: tuple = (-0.5, 0.5)

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

        if self.logger is not None and value is not None:
            self.logger.debug(f"Motion planning triggered (phase name: {value})")

    # prohibit reassignment of the phases dict and make sure input types are correct
    @property
    def phases(self) -> dict[str, MPPhaseContainer]:
        for k, v in self.state._phases.items():
            if not isinstance(k, str):
                raise TypeError("Phase keys must be str")
            if not isinstance(v, MPPhaseContainer):
                raise TypeError("Phase values must be MPPhaseContainer")
        return self.state._phases