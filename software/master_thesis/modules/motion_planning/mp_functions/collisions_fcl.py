import numpy as np
import fcl
from master_thesis.containers.general_containers.frodo_agent_container import FRODOAgentContainer
from master_thesis.containers.general_containers.environment_container import EnvironmentContainer
from master_thesis.containers.general_containers.obstacle_container import ObstacleContainer


class AgentCollisionChecker():
    """Pure raw-data collision checker — no container dependencies.

    All geometry is passed as plain dicts with keys: x, y, psi, length, width, height.
    """

    def __init__(self, agent_dims: tuple[float, float, float], obstacles: list[dict]):
        length, width, height = agent_dims
        geometry = fcl.Box(length, width, height)
        self.agent_objs = [fcl.CollisionObject(geometry, fcl.Transform())]
        self.agent_manager = self._create_manager(self.agent_objs)
        self.collisions_list = []
        self.env_objects = []
        self.env_manager = self._create_manager([])
        self.refresh_env_manager(obstacles)

    def refresh_env_manager(self, obstacles: list[dict], frozen_agents: list[dict] | None = None):
        """Rebuild the environment collision manager.

        Args:
            obstacles:     Static obstacle dicts (x, y, psi, length, width, height).
            frozen_agents: Agent dicts to treat as static obstacles.
        """
        env_objs = self._build_env_objects(obstacles, frozen_agents)
        self.env_objects = env_objs
        self.env_manager = self._create_manager(env_objs)

    def _build_env_objects(self, obstacles: list[dict], frozen_agents: list[dict] | None = None) -> list:
        objs = []
        for obs in obstacles:
            geom = fcl.Box(obs['length'], obs['width'], obs['height'])
            q = [np.cos(obs['psi'] / 2), 0, 0, np.sin(obs['psi'] / 2)]
            pos = [obs['x'], obs['y'], 0.0]
            objs.append(fcl.CollisionObject(geom, fcl.Transform(q, pos)))
        if frozen_agents:
            for agent in frozen_agents:
                geom = fcl.Box(agent['length'], agent['width'], agent['height'])
                q = [np.cos(agent['psi'] / 2), 0, 0, np.sin(agent['psi'] / 2)]
                pos = [agent['x'], agent['y'], 0.0]
                objs.append(fcl.CollisionObject(geom, fcl.Transform(q, pos)))
        return objs

    def check_state(self, testing_state):  # state = [x, y, psi]
        """Check a single configuration for collision."""
        x, y, psi = testing_state
        q = [np.cos(psi / 2), 0, 0, np.sin(psi / 2)]
        self.agent_objs[0].setTransform(fcl.Transform(q, [x, y, 0.0]))
        self.agent_manager.update()

        req = fcl.CollisionRequest(num_max_contacts=1, enable_contact=False)
        data = fcl.CollisionData(request=req)
        self.agent_manager.collide(self.env_manager, data, fcl.defaultCollisionCallback)
        return data.result.is_collision

    def check_state_ompl(self, state):
        x = state.getX()
        y = state.getY()
        theta = state.getYaw()
        return not self.check_state([x, y, theta])

    def clearance_for_state(self, x: float, y: float, psi: float) -> float:
        """Minimum distance from agent footprint at (x, y, psi) to any obstacle.

        Returns 0.0 when in collision, positive otherwise.
        Used by OMPL's MaximizeMinClearanceObjective via FCLStateValidityChecker.
        """
        q = [np.cos(psi / 2), 0, 0, np.sin(psi / 2)]
        self.agent_objs[0].setTransform(fcl.Transform(q, [x, y, 0.0]))

        min_dist = float('inf')
        for env_obj in self.env_objects:
            req = fcl.DistanceRequest()
            res = fcl.DistanceResult()
            fcl.distance(self.agent_objs[0], env_obj, req, res)
            min_dist = min(min_dist, res.min_distance)
        return max(0.0, min_dist)

    def broadphase_collision_checking(self, states):
        self.collisions_list = [self.check_state(state) for state in states]

    @staticmethod
    def _create_manager(objects: list):
        manager = fcl.DynamicAABBTreeCollisionManager()
        manager.registerObjects(objects)
        manager.setup()
        return manager

# TODO: make all this a single checker? 
class WorldCollisionChecker:

    def __init__(self, env_cont: EnvironmentContainer):
        self.env_cont = env_cont

        self.manager = fcl.DynamicAABBTreeCollisionManager()

        self.initialize_objects()

        self.manager.setup()

    def initialize_objects(self):

        self.agent_objs: dict[str, fcl.CollisionObject] = {}
        self.obstacle_objs: dict[str, fcl.CollisionObject] = {}
        self.obj_to_id: dict[fcl.CollisionObject, str] = {}

        # initialize all obstacles (static)
        for oid, obs in self.env_cont.state.obstacle_conts.items():
            self.add_obstacle(obs, oid)

        # initialize all agents (dynamic)
        for aid, ag in self.env_cont.state.agent_conts.items():
            self.add_agent(ag, aid)

    def add_agent(self, agent_container: FRODOAgentContainer, agent_id: str):
        obj = self._make_box(agent_container.config, agent_container.state)
        
        self.agent_objs[agent_id] = obj
        self.obj_to_id[obj] = agent_id

        self.manager.registerObjects([obj])
        self.manager.update()

    def add_obstacle(self, obstacle_container: ObstacleContainer, obstacle_id: str):
        obj = self._make_box(obstacle_container.config, obstacle_container.state)

        self.obstacle_objs[obstacle_id] = obj
        self.obj_to_id[obj] = obstacle_id

        self.manager.registerObjects([obj])
        # obstacles typically do not move → no update() required

    def _make_box(self, config, state):
        geom = fcl.Box(config.length, config.width, config.height)

        # Obstacles keep pose in config (state=None); agents keep pose in state.
        pose = state if state is not None else config
        q = [np.cos(pose.psi / 2), 0, 0, np.sin(pose.psi / 2)]
        pos = [pose.x, pose.y, 0.0]

        tf = fcl.Transform(q, pos)
        return fcl.CollisionObject(geom, tf)
    
    def update(self):
        # only dynamic agents
        for aid, obj in self.agent_objs.items():
            st = self.env_cont.state.agent_conts[aid].state

            q = [np.cos(st.psi / 2), 0, 0, np.sin(st.psi / 2)]
            pos = [st.x, st.y, 0.0]

            obj.setTransform(fcl.Transform(q, pos))

        self.manager.update()

    def _run_check(self) -> dict:
        """Run collision detection on the current manager state and return results.

        The result dict has one entry per agent.  Values are lists of colliding
        object IDs (other agents *or* obstacles).  Obstacles never appear as keys.
        """
        collisions = {aid: [] for aid in self.agent_objs.keys()}

        req = fcl.CollisionRequest(num_max_contacts=1, enable_contact=False)
        data = fcl.CollisionData(request=req)

        def cb(o1, o2, data):
            a = self.obj_to_id.get(o1)
            b = self.obj_to_id.get(o2)
            if a and b and a != b:
                # Only update the entries that exist (agents); obstacles have no key.
                if a in collisions:
                    collisions[a].append(b)
                if b in collisions:
                    collisions[b].append(a)
            return False

        self.manager.collide(self.manager, data, cb)
        return collisions

    def check_all(self):
        return self._run_check()

    def check_prospective(self, prospective: dict[str, tuple[float, float, float]]) -> dict:
        """Check prospective next-tick positions without committing to container state.

        Sets agent transforms to the prospective positions, runs collision detection,
        then restores the transforms to the current container state.

        Args:
            prospective: {agent_id: (x, y, psi)} map of where each agent would move.

        Returns:
            Same collision dict as check_all(): {agent_id: [list of colliding ids]}.
        """
        for aid, (x, y, psi) in prospective.items():
            q = [np.cos(psi / 2), 0, 0, np.sin(psi / 2)]
            self.agent_objs[aid].setTransform(fcl.Transform(q, [x, y, 0.0]))
        self.manager.update()

        result = self._run_check()

        # Restore transforms from container state
        for aid, obj in self.agent_objs.items():
            st = self.env_cont.state.agent_conts[aid].state
            q = [np.cos(st.psi / 2), 0, 0, np.sin(st.psi / 2)]
            obj.setTransform(fcl.Transform(q, [st.x, st.y, 0.0]))
        self.manager.update()

        return result