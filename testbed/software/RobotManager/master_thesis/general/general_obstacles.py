from extensions.simulation.src.core.environment import Object
import extensions.simulation.src.core.spaces as spaces
from dataclasses import dataclass
from applications.FRODO.simulation.frodo_simulation import FRODO_SimulationObject

class GeneralObstacle(FRODO_SimulationObject):
    object_type = "obstacle"
    static = True

    def __init__(self, obstacle_id: str, x: float, y: float, config: Obstacle_Config | None = None, *args):
        if config is None:
            config = Obstacle_Config()

        self.space = spaces.Space2D()

        # define geometry / footprint
        self.space.dimensions[0].limits = [
            [-config.length/2, config.length/2],
            [-config.width/2, config.width/2]
        ]

        super().__init__(object_id=obstacle_id, space=self.space)
        
        self.obstacle_id = obstacle_id
        self.agent_id = obstacle_id
        self.config = config
        self.size = max(config.length, config.width)
        
        # Initialize state
        self.state = Obstacle_State(x=x, y=y, psi=0.0)
        
        # Set position in the space
        self.setPosition(x, y)

    def set_state(self, x: float = None, y: float = None, psi: float = None):
        if x is not None:
            self.state.x = x
        if y is not None:
            self.state.y = y
        if psi is not None:
            self.state.psi = psi

    def output(self, env):
        """Populate configuration_global for collision detection."""
        # Update the local configuration from the current state
        if hasattr(self, '_configuration') and self._configuration is not None:
            self._configuration['pos'] = [self.state.x, self.state.y]
            if hasattr(self._configuration, 'ori') or 'ori' in dir(self._configuration):
                self._configuration['ori'] = [self.state.psi]
