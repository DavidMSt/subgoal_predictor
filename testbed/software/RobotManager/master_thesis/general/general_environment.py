# third party
import numpy as np

# bilbolab
from applications.FRODO.simulation.frodo_simulation import FRODO_Simulation, FRODO_ENVIRONMENT_ACTIONS, FrodoEnvironment, FRODO_Static, FRODO_Simulation_Events
from extensions.simulation.src.core.environment import Object
from extensions.simulation.src.objects.frodo.frodo import FRODO_DynamicAgent
import extensions.simulation.src.core as core
import extensions.simulation.src.core.environment as core_env

from extensions.simulation.src.core.environment import BASE_ENVIRONMENT_ACTIONS

# master thesis
from master_thesis.general.general_agent import FRODOGeneralAgent, FRODO_Agent_Config, FRODO_GeneralAgent_CommandSet
from master_thesis.general.general_obstacle import GeneralObstacle
from master_thesis.modules.motion_planning.helper.collisions_fcl import WorldCollisionChecker
from master_thesis.containers.general_containers.environment_container import EnvironmentConfig, EnvironmentContainer
from master_thesis.general.general_task import GeneralTask

from master_thesis.containers.base_container import BaseContainer
from master_thesis.containers.general_containers.local_world_container import (
                    LocalWorldContainer, LocalWorldConfig, LocalWorldState
                )

# ======================================================================================================================

class FrodoGeneralEnvironment(FrodoEnvironment):
    environment_container : EnvironmentContainer

    def __init__(self, Ts, run_mode, limits: tuple[tuple[int, int], ...] = ((-5, 5), (-5, 5)), *args, **kwargs):
        super().__init__(Ts=Ts, run_mode=run_mode, *args, **kwargs)
        self.space = core.spaces.Space2D()
        self._obstacles = []  # TODO: still needed? 

        self.set_limits(limits)
        environment_config = EnvironmentConfig(limits=limits, Ts = Ts)
        self.environment_container = EnvironmentContainer(environment_config) 
        
        # Initialize collision checker after parent init (when self.objects exists)
        self.collision_checker = self.setup_collision_checker()

        # Initialize occupancy grids
        self.initialize_occupancy_grids()

        core.scheduling.Action(action_id=FRODO_ENVIRONMENT_ACTIONS.COLLISION, #TODO: initialize it like this?
                        object=self,
                        function=self._collision_checking,
                        priority=65,
                        parent=self.scheduling.actions['objects'])
        
        core.scheduling.Action(action_id=FRODO_ENVIRONMENT_ACTIONS.COMMUNICATION, #TODO: initialize it like this?
                        object=self,
                        function=self._update_lw_function,
                        priority=31,
                        parent=self.scheduling.actions['objects'])

    def _update_lw_function(self):
        """
        Update each agent's local world container based on sensing ranges.

        Operates purely on containers:
        - Reads agent/task/obstacle containers from environment_container.state
        - Filters containers by distance using agent positions from containers
        - Assigns filtered container references to each agent's local world state

        For each agent, populate its local world state with:
        - Nearby agents (within agent_range)
        - Nearby tasks (within task_range)
        - Nearby obstacles (within obstacle_range, or all if None)

        Ranges are defined in environment_container.config.
        """
        def filter_by_range(agent_x: float, agent_y: float,
                        containers: dict, range_limit: float | None) -> dict:
            """
            Filter containers by distance from agent position.

            Args:
                agent_x, agent_y: Agent position (from agent container)
                containers: Dictionary of containers with x, y attributes (via BaseContainer.__getattr__)
                range_limit: Maximum distance (None = infinite range, return all)

            Returns:
                Filtered dictionary of container references within range
            """
            if range_limit is None:
                # Infinite range - return all containers
                return containers.copy()

            filtered = {}
            for obj_id, obj_cont in containers.items():
                # Access x, y from container (forwards to config/state via BaseContainer)
                dist = np.sqrt((obj_cont.x - agent_x)**2 + (obj_cont.y - agent_y)**2)
                if dist <= range_limit:
                    filtered[obj_id] = obj_cont

            return filtered

        env_config = self.environment_container.config
        env_state = self.environment_container.state

        # Iterate over agent containers in environment state
        for _, agent in self.agents.items():
            assert isinstance(agent, FRODOGeneralAgent)

            lwr_cont = agent.lwr_cont
            assert isinstance(lwr_cont, LocalWorldContainer)
            
            # Get agent's position
            agent_x = agent.state.x
            agent_y = agent.state.y

            # Update nearby agent containers (excluding self)
            nearby_agents = filter_by_range(
                agent_x, agent_y,
                env_state.agent_conts,
                env_config.agent_range
            )
            # Remove self from neighbors
            nearby_agents.pop(agent.agent_id, None) # don't pop anymore
            lwr_cont.neighbors = nearby_agents

            # Update nearby task containers
            lwr_cont.state.tasks = filter_by_range(
                agent_x, agent_y,
                env_state.task_conts,
                env_config.task_range
            )

            # Update nearby obstacle containers
            lwr_cont.state.obstacles = filter_by_range(
                agent_x, agent_y,
                env_state.obstacle_conts,
                env_config.obstacle_range
            )

    def action_output(self):
        for obj in self.objects.values():
            obj.output(self)

    def addObject(self, objects: core_env.Object | list[Object]):
        assert self.collision_checker is not None

        self.check_limits(objects.container.x, objects.container.y)

        if isinstance(objects, FRODOGeneralAgent):
            # Add agent to environment container
            self.environment_container.add_agents(objects.container)
            self.collision_checker.add_agent(objects.container, objects.agent_id)

            # Initialize local world container for agent
            objects.lwr_cont = LocalWorldContainer(
                config=LocalWorldConfig(limits=self.environment_container.limits),
                state=LocalWorldState()
            )

        elif isinstance(objects, GeneralObstacle):
            self.environment_container.add_obstacles(objects.container)

        elif isinstance(objects, GeneralTask):
            self.environment_container.add_tasks(objects.container)

        return super().addObject(objects)

    def setup_collision_checker(self)-> WorldCollisionChecker:
        agents = {}
        obstacles = {}

        for obj_id, obj in self.objects.items():
            if isinstance(obj, FRODOGeneralAgent):
                agents[obj_id] = obj
            elif isinstance(obj, GeneralObstacle):
                obstacles[obj_id] = obj
            else:
                raise AssertionError("Unknown object class during env collision checker setup")

        collision_checker = WorldCollisionChecker(self.environment_container)

        self.logger.info(
            f"Collision checker initialized with {len(agents)} agents and {len(obstacles)} obstacles."
        )
        return collision_checker

    def set_limits(self, limits: tuple[tuple[int, int], ...] = ((-3, 3), (-3, 3)), wrapping = [False, False]):
        # check if limits are valid
        for i, limit in enumerate(limits):
            if limit[0] > limit[1]:
                self.logger.error(f"Invalid environment limits for dimension: {i}: {limit[0]} > {limit[1]}")

        pos_dim = self.space.dimensions[0] # Get the first dimension of the space (E(2) vector)
        pos_dim.kwargs['wrapping'] = wrapping
        pos_dim.limits = limits

        # Keep environment container config in sync (config is frozen, so replace it)
        if hasattr(self, 'environment_container'):
            from dataclasses import replace
            self.environment_container.config = replace(self.environment_container.config, limits=limits)

    def check_limits(self, x: float, y: float):
        (xmin, xmax), (ymin, ymax) = self.limits

        if not (xmin <= x <= xmax):
            raise ValueError(
                f"[ENV ERROR] x={x} outside allowed range [{xmin}, {xmax}]"
            )

        if not (ymin <= y <= ymax):
            raise ValueError(
                f"[ENV ERROR] y={y} outside allowed range [{ymin}, {ymax}]"
            )

    def action_input(self):
        # print(f"=== ENV INPUT PHASE @ tick {self.scheduling.tick}") # TODO: enabling this shows that this phase is called twice? bug? 
        self.logger.debug(f"{self.scheduling.tick}: Action Frodo Input")

    def _collision_checking(self):
        if self.collision_checker is None:
            return

        self.collision_checker.update()
        collisions = self.collision_checker.check_all()

        for aid, hits in collisions.items():
            if hits:
                print(f"[COLLISION] Agent {aid} collided with {hits}")

    @property
    def limits(self) ->list[list[float]]:
        return self.space.dimensions[0].limits
    
    @property
    def environment_configuration(self) -> EnvironmentConfig:
        return EnvironmentConfig(
            limits= self.limits.copy(),
            obstacles = self.obstacles,
            Ts = self.Ts
        )

    def initialize_occupancy_grids(self):
        """Initialize both occupancy grids based on workspace limits and grid resolution."""
        container = self.environment_container
        x_lim = container.limits[0]
        y_lim = container.limits[1]

        # Calculate grid dimensions with padding
        x_min = x_lim[0] - container.grid_padding
        x_max = x_lim[1] + container.grid_padding
        y_min = y_lim[0] - container.grid_padding
        y_max = y_lim[1] + container.grid_padding

        n_x = int(np.ceil((x_max - x_min) / container.grid_resolution))
        n_y = int(np.ceil((y_max - y_min) / container.grid_resolution))

        # Initialize both grids as free (False = free, True = occupied)
        container.occupancy_grid_full = np.zeros((n_y, n_x), dtype=bool)
        container.occupancy_grid_static = np.zeros((n_y, n_x), dtype=bool)

        self.logger.info(f"Initialized occupancy grids: {n_y}x{n_x} cells ({container.grid_resolution}m resolution)")

    def world_to_grid(self, x: float, y: float) -> tuple[int, int]:
        """Convert world coordinates to grid indices."""
        container = self.environment_container
        x_lim = container.limits[0]
        y_lim = container.limits[1]

        x_min = x_lim[0] - container.grid_padding
        y_min = y_lim[0] - container.grid_padding

        grid_x = int(np.floor((x - x_min) / container.grid_resolution))
        grid_y = int(np.floor((y - y_min) / container.grid_resolution))

        return grid_y, grid_x  # Note: row, col format for numpy arrays

    def grid_to_world(self, grid_y: int, grid_x: int) -> tuple[float, float]:
        """Convert grid indices to world coordinates (cell center)."""
        container = self.environment_container
        x_lim = container.limits[0]
        y_lim = container.limits[1]

        x_min = x_lim[0] - container.grid_padding
        y_min = y_lim[0] - container.grid_padding

        x = x_min + (grid_x + 0.5) * container.grid_resolution
        y = y_min + (grid_y + 0.5) * container.grid_resolution

        return x, y

    def mark_object_in_grid(self, x: float, y: float, psi: float, length: float, width: float,
                           mark_full: bool = True, mark_static: bool = False):
        """
        Mark cells occupied by an object in the occupancy grids.

        Args:
            x, y, psi: Object pose
            length, width: Object dimensions
            mark_full: Whether to mark in occupancy_grid_full
            mark_static: Whether to mark in occupancy_grid_static
        """
        container = self.environment_container

        # Compute object's corner points in world frame
        # Assuming object center at (x, y) with orientation psi
        half_l, half_w = length / 2, width / 2
        corners_local = np.array([
            [half_l, half_w],
            [half_l, -half_w],
            [-half_l, -half_w],
            [-half_l, half_w]
        ])

        # Rotation matrix
        cos_psi, sin_psi = np.cos(psi), np.sin(psi)
        R = np.array([[cos_psi, -sin_psi], [sin_psi, cos_psi]])

        # Transform to world frame
        corners_world = (R @ corners_local.T).T + np.array([x, y])

        # Find bounding box in world coordinates
        x_min, y_min = corners_world.min(axis=0)
        x_max, y_max = corners_world.max(axis=0)

        # Convert to grid coordinates
        grid_y_min, grid_x_min = self.world_to_grid(x_min, y_min)
        grid_y_max, grid_x_max = self.world_to_grid(x_max, y_max)

        # Mark all cells in bounding box (conservative approach)
        grid_shape = container.occupancy_grid_full.shape
        for gy in range(max(0, grid_y_min), min(grid_shape[0], grid_y_max + 1)):
            for gx in range(max(0, grid_x_min), min(grid_shape[1], grid_x_max + 1)):
                if mark_full:
                    container.occupancy_grid_full[gy, gx] = True
                if mark_static:
                    container.occupancy_grid_static[gy, gx] = True

    def is_position_free(self, x: float, y: float, psi: float, length: float, width: float,
                        check_grid: str = 'full') -> bool:
        """
        Check if a position is collision-free using the occupancy grid.

        Args:
            x, y, psi: Pose to check
            length, width: Object dimensions
            check_grid: Which grid to check ('full' or 'static')

        Returns:
            True if position is free, False if occupied
        """
        container = self.environment_container
        grid = (container.occupancy_grid_full if check_grid == 'full'
                else container.occupancy_grid_static)

        # Compute object's bounding box
        half_l, half_w = length / 2, width / 2
        corners_local = np.array([
            [half_l, half_w],
            [half_l, -half_w],
            [-half_l, -half_w],
            [-half_l, half_w]
        ])

        cos_psi, sin_psi = np.cos(psi), np.sin(psi)
        R = np.array([[cos_psi, -sin_psi], [sin_psi, cos_psi]])
        corners_world = (R @ corners_local.T).T + np.array([x, y])

        x_min, y_min = corners_world.min(axis=0)
        x_max, y_max = corners_world.max(axis=0)

        grid_y_min, grid_x_min = self.world_to_grid(x_min, y_min)
        grid_y_max, grid_x_max = self.world_to_grid(x_max, y_max)

        # Check all cells in bounding box
        grid_shape = grid.shape
        for gy in range(max(0, grid_y_min), min(grid_shape[0], grid_y_max + 1)):
            for gx in range(max(0, grid_x_min), min(grid_shape[1], grid_x_max + 1)):
                if grid[gy, gx]:
                    return False  # Cell is occupied

        return True  # All cells are free