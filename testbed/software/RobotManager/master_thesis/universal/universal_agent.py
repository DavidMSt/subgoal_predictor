from typing import List
from general.general_agents import FRODOGeneralAgent
from motion_planning.mp_agent import MPAgentModule
from task_assignment.task_agent import AssignmentAgentModule

class FRODOUniversalAgent(FRODOGeneralAgent):
    def __init__(self, start_config: List[float], fov_deg=360, view_range=1.5, runner: bool = True, *args, **kwargs) -> None:
        super().__init__(start_config, fov_deg, view_range, runner, *args, **kwargs)
        self.mpi = ...
        self.asi = ...
        self.exi = ... # TODO


# def main():
#     ...

# if __name__ == "__main__":
#     main()

