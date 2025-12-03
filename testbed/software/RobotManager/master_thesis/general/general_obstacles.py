from extensions.simulation.src.core.environment import Object
import extensions.simulation.src.core.spaces as spaces
from dataclasses import dataclass
# from applications.FRODO.simulation.frodo_simulation import FRODO_SimulationObject
from extensions.simulation.src.core.environment import Object
from testbed.software.RobotManager.master_thesis.general.containers.obstacle_container import ObstacleContainer, Obstacle_Config

class GeneralObstacle(Object):
    object_type = "obstacle"
    static = True #TODO: This could be removed

    def __init__(self, obstacle_id: str, x: float, y:float, psi:float, length:float, width:float, height:float):
        
        self.obstacle_id = obstacle_id

        # bilbolab geometry
        self.space = spaces.Space2D()
        self.space.dimensions[0].limits = [
            [-length / 2, length / 2],
            [-width / 2,  width / 2]
        ]

        super().__init__(object_id=obstacle_id, space=self.space)

        # self.state = Obstacle_State( # TODO: do I really need the state here still? 
        #     x=x,
        #     y=y,
        #     psi=psi
        # )

        self.setPosition(x, y)


        obstacle_config = Obstacle_Config(
            x = x,
            y = y,
            psi = psi,
            length= length,
            width= width,
            height = height
        )

        self.container = ObstacleContainer(object_id = self.object_id, config=obstacle_config)



    # def set_state(self, x: float = None, y: float = None, psi: float = None):
    #     if x is not None:
    #         self.state.x = x
    #     if y is not None:
    #         self.state.y = y
    #     if psi is not None:
    #         self.state.psi = psi

    def output(self, env):
        pass
        # if hasattr(self, '_configuration') and self._configuration is not None:
        #     self._configuration['pos'] = [self.state.x, self.state.y]
        #     self._configuration['ori'] = [self.state.psi]
