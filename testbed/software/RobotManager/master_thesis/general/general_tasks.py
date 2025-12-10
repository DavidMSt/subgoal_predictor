import numpy as np
from extensions.simulation.src.core.environment import Object
import extensions.simulation.src.core as core

from master_thesis.containers.general_containers.task_container import TaskContainer, Task_Config

# ----------------------------- Task Classes -----------------------------

class GeneralTask(Object):
    def __init__(self, id, x: float, y: float, psi: float, *, is_assignable: bool = True):
        self.space = core.spaces.Space2D()  # quick fix TODO: make clean once Object handles this correctly
        super().__init__(object_id=id, space=self.space)

        task_config = Task_Config(x=x, y=y, psi=psi)
        self.container = TaskContainer(object_id=id, config=task_config)

    def output(self, env):
        """Output method required by environment scheduler. Tasks have no output behavior, therefore dummy ."""
        pass

    def _poll_assignment_status_action(self): # TODO: poll here the assignment status to change the color? 
        ...

if __name__ == "__main__":
    t1 = GeneralTask(id='task_test', x=10.3, y=2.3, psi=np.pi)
    t2 = GeneralTask(id='task_test2', x=1.3, y=-1.3, psi=3*np.pi)

    print(f"Task 1 container: {t1.container}")
    print(f"Task 2 container: {t2.container}")
