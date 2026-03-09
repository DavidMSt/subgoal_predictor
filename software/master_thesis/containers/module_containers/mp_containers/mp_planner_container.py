from dataclasses import dataclass, field
import numpy as np
from collections import OrderedDict

from core.utils.logging_utils import Logger
from master_thesis.containers.base_container import BaseContainer
from master_thesis.containers.module_containers.mp_containers.mp_phase_container import MPPhaseContainer
from master_thesis.modules.motion_planning.mp_functions.ompl_planner import OMPLPlannerConfig

@dataclass(frozen = False, slots=True)
class AgentMPPlannerState:

    # keep all planned phases
    _phases: OrderedDict[str, MPPhaseContainer] = field(default_factory=OrderedDict)

    # Phase name for motion planning action (None = no planning, string = plan with this phase name)
    _start_planning: str | None = None


@dataclass(frozen = True, slots = True)
class AgentMPPlannerConfig:
    planner_config: OMPLPlannerConfig = field(default_factory=OMPLPlannerConfig)

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