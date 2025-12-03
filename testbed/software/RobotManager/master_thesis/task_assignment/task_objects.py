import numpy as np
from extensions.simulation.src.core.environment import Object
import extensions.simulation.src.core as core

from master_thesis.containers.task_container import TaskContainer, Task_Config

# ----------------------------- Task Classes -----------------------------

class Task(Object):
    def __init__(self, id, x, y, psi, *, is_assignable: bool = True):
        self.space = core.spaces.Space2D()  # quick fix TODO: make clean once Object handles this correctly
        super().__init__(object_id=id, space=self.space)

        task_config = Task_Config(x=x, y=y, psi=psi)
        self.container = TaskContainer(object_id=id, config=task_config)

if __name__ == "__main__":
    t1 = Task(id='task_test', x=10.3, y=2.3, psi=np.pi)
    t2 = Task(id='task_test2', x=1.3, y=-1.3, psi=3*np.pi)

    print(f"Task 1 container: {t1.container}")
    print(f"Task 2 container: {t2.container}")
