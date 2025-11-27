from extensions.simulation.src.core.environment import Object
import extensions.simulation.src.core.spaces as spaces
from dataclasses import dataclass
from applications.FRODO.simulation.frodo_simulation import FRODO_SimulationObject
from master_thesis.general.containers.obstacle_containers import ObstacleContainer, Obstacle_Config

class GeneralObstacle(FRODO_SimulationObject):
    object_type = "obstacle"
    static = True

    def __init__(self, obstacle_id: str, container: ObstacleContainer):
        cfg = container.config

        # geometry
        self.space = spaces.Space2D()
        self.space.dimensions[0].limits = [
            [-cfg.length / 2, cfg.length / 2],
            [-cfg.width / 2,  cfg.width / 2]
        ]

        super().__init__(object_id=obstacle_id, space=self.space)

        self.container = container

        self.state = Obstacle_State(
            x=cfg.x0,
            y=cfg.y0,
            psi=cfg.psi0
        )

        self.setPosition(cfg.x0, cfg.y0)

    def set_state(self, x: float = None, y: float = None, psi: float = None):
        if x is not None:
            self.state.x = x
        if y is not None:
            self.state.y = y
        if psi is not None:
            self.state.psi = psi

    def output(self, env):
        if hasattr(self, '_configuration') and self._configuration is not None:
            self._configuration['pos'] = [self.state.x, self.state.y]
            self._configuration['ori'] = [self.state.psi]
