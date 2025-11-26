import numpy as np
import fcl
from master_thesis.general.configuration_containers import EnvironmentConfig, FRODO_Agent_Config
from master_thesis.general.general_obstacles import GeneralObstacle
# import meshcat.transformations as tf

class CollisionChecker():

    def __init__(self, agent_config, env_config):
        self.env_config: EnvironmentConfig = env_config  
        self.agent_config: FRODO_Agent_Config = agent_config
        self.collisions_list = [] # initialize dynamic collison list
        self.initialize_collision_manager(env_config, agent_config)

    def set_plan(self, plan): # TODO: Remove? 
        # self._plan = plan
        self.states = plan["plan"]["states"]

    def initialize_collision_manager(self, env_config, agent_config):
        self.initialize_env_manager(env_config)
        self.initialize_agent_manager(agent_config)

    def initialize_agent_manager(self, agent_config):
        # py-fcl does not expose the objects in a manager for update, therefore they must be accesible here
        self.agent_objs = self.create_agent_objects(agent_config)

        self.agent_manager = self.create_collision_manager(self.agent_objs)


    def initialize_env_manager(self, env_config: EnvironmentConfig):
        # Defensive programming: check for 'obstacles' attribute
        if not hasattr(env_config, "obstacles"):
            raise AttributeError("Provided env has no 'obstacles' attribute")
        obstacle_objects_list = self.create_environment_objects()
        self.env_manager = self.create_collision_manager(obstacle_objects_list)
    
    def check_state(self, testing_state):  # state = [x, y, psi]
        """Check a single configuration for collision."""

        x, y, psi = testing_state

        # ----------------------------------------------------
        # 1) Update the transform of the single agent object
        # ----------------------------------------------------
        q = [np.cos(psi / 2), 0, 0, np.sin(psi / 2)]
        pos = [x, y, 0.0]

        tf = fcl.Transform(q, pos)

        
        agent_obj = self.agent_objs[0]
        agent_obj.setTransform(tf)
        self.agent_manager.update()


        # ----------------------------------------------------
        # 2) Perform the actual collision check
        # ----------------------------------------------------
        req = fcl.CollisionRequest(num_max_contacts=1, enable_contact=False)
        data = fcl.CollisionData(request=req)

        self.agent_manager.collide(self.env_manager, data, fcl.defaultCollisionCallback)

        return data.result.is_collision
    
    def check_state_ompl(self, state):
        x = state.getX()
        y = state.getY()
        theta = state.getYaw()
        config = [x, y, theta]


        valid = self.check_state(config)

        return not valid # ompl expects collision as return here

    # def check_states(self, states):
    #     """Check multiple configurations"""
    #     return [self.check_state(s) for s in states]

    def broadphase_collision_checking(self, states):
        self.collisions_list = [self.check_state(state) for state in states]

    # def create_agent_objects(self, state):
    #     objs = self.create_objects_frodo(state)

    #     return objs

    def create_environment_objects(self):
        obstacle_list = []
        for obstacle in self.env_config.obstacles:
            _obs = self.create_env_collision_object(obstacle)
            obstacle_list.append(_obs)
        return obstacle_list
    
    def create_agent_objects(self, agent_config):
        """
        Create the initial FCL collision object for the FRODO agent.
        The agent is initialized at state (0,0,0) and its transform
        will be updated later inside check_state().
        """
        # --- create a zero state for initialization ---
        class _ZeroState:
            def __init__(self):
                self.x = 0.0
                self.y = 0.0
                self.psi = 0.0

        zero_state = _ZeroState()


        obj = self.create_collision_box(agent_config, zero_state)
        return [obj]
    
    def create_env_collision_object(self, obstacle):
        if isinstance(obstacle, GeneralObstacle):
            _obs = self.create_collision_box(config = obstacle.config, state = obstacle.state)
        else:
            raise ValueError
        return _obs

    @staticmethod
    def create_collision_box(config, state, q=None):
        # FCL box expects (x_size, y_size, z_size)
        geometry = fcl.Box(config.length, config.width, config.height)

        # position
        pos = [state.x, state.y, 0.0]

        # orientation
        if q is None:
            # default rotation: yaw = state.psi
            yaw = state.psi
            q = [np.cos(yaw / 2), 0, 0, np.sin(yaw / 2)]

        # create transform
        transform = fcl.Transform(q, pos)

        return fcl.CollisionObject(geometry, transform)

    @staticmethod
    def create_collision_manager(objects: list):
        manager = fcl.DynamicAABBTreeCollisionManager()
        manager.registerObjects(objects)
        manager.setup()
        return manager

# TODO: make all this a single checker? 
class EnvironmentCollisionChecker:

    def __init__(self, compute_closest_distance = False):
        self.static_objs = {}
        self.dynamic_objs = {}
        self.dynamic_refs = {}
        self.manager = fcl.DynamicAABBTreeCollisionManager()
        self.dim = None  # filled at initialize()
        
        if compute_closest_distance: 
            self.closest_objects: dict[str, float] | None = {}

        else: 
            self.closest_object = None
            self.closest_agent = None

    # ----------------------------------------------------------------------
    # INITIALIZATION
    # ----------------------------------------------------------------------
    def initialize(self, agents, obstacles):
        """
        Called ONCE before simulation starts.
        Extract robot dimensions from agent_config.
        Build the static objects once.
        """
        # --- store dimensions from ANY agent (all same for now)
        if len(agents) > 0:
            ag0 = next(iter(agents.values()))
            self.dim = {
                "L": ag0.agent_config.length,
                "W": ag0.agent_config.width,
                "H": ag0.agent_config.height,
            }
        else:
            raise RuntimeError("CollisionChecker.initialize() called with no agents.")

        # --- build static objects once
        for oid, obs in obstacles.items():
            obj = self._make_obstacle_obj(obs)
            self.static_objs[oid] = obj

        # dynamic objects will be rebuilt every check, so nothing stored here

        # Build a static manager for obstacles only
        self.manager.registerObjects(list(self.static_objs.values()))
        self.manager.setup()

    # ----------------------------------------------------------------------
    # RL Observation space augmentations
    # ----------------------------------------------------------------------
    def distance_and_bearing_to_closest_obstacle(self, agent):
        min_dist = float('inf')
        angle = 0.0

        for obst in self.static_objs.values():
            dist, p_agent, p_obst = self.compute_distance(agent, obst)

            if dist < min_dist:
                min_dist = dist
                # direction: from agent to obstacle nearest point
                vec = p_obst - np.array([agent.state.x, agent.state.y])
                angle = np.atan2(vec[1], vec[0]) - agent.state.psi

        return min_dist, angle
    
    def compute_distance(self, agent, obstacle):
        req = fcl.DistanceRequest(enable_nearest_points=True)
        res = fcl.DistanceResult()
        fcl.distance(req, res, agent.fcl_obj, obstacle.fcl_obj)
        return res.min_distance, np.array(res.nearest_points[0]), np.array(res.nearest_points[1])

    def distance_and_bearing_to_closest_agent(self, agent, agents_dict):
        min_dist = float('inf')
        angle = 0.0

        for other in agents_dict.values():
            if other is agent:
                continue

            dist, p_self, p_other = self.compute_distance(agent, other)

            if dist < min_dist:
                min_dist = dist
                vec = p_other - np.array([agent.state.x, agent.state.y])
                angle = np.atan2(vec[1], vec[0]) - agent.state.psi

        return min_dist, angle

    # ----------------------------------------------------------------------
    # MAIN CHECK FUNCTION
    # ----------------------------------------------------------------------
    def check_all(self, agents, obstacles):
        """
        agents: dict[str, FRODOGeneralAgent]
        obstacles: dict[str, GeneralObstacle]

        Returns:
            dict: agent_id -> list of collided object IDs
        """
        fcl_objects, id_from_obj = self._build_fcl_objects(agents, obstacles)

        # New manager including dynamic + static objects
        manager = fcl.DynamicAABBTreeCollisionManager()
        manager.registerObjects(list(fcl_objects.keys()))
        manager.setup()

        collisions: dict[str, list[str]] = {aid: [] for aid in agents.keys()}

        def cb(objA, objB, data):
            # map back to IDs; ignore objects we didn't track
            a = id_from_obj.get(objA)
            b = id_from_obj.get(objB)
            if a is None or b is None:
                return False

            if a in collisions and b not in collisions[a]:
                collisions[a].append(b)
            if b in collisions and a not in collisions[b]:
                collisions[b].append(a)

            # False => continue checking
            return False

        # create request/data and run self-collision
        req = fcl.CollisionRequest(num_max_contacts=1, enable_contact=False)
        data = fcl.CollisionData(request=req)
        # perform a manager–manager collision check (self-collision)
        req = fcl.CollisionRequest(num_max_contacts=1, enable_contact=False)
        data = fcl.CollisionData(request=req)
        manager.collide(manager, data, cb)

        return collisions

    # ----------------------------------------------------------------------
    # INTERNAL: Build all objects for a single check
    # ----------------------------------------------------------------------
    def _build_fcl_objects(self, agents, obstacles):
        """
        Returns:
            fcl_objects: dict[fcl.CollisionObject, None]
            id_from_obj: dict[fcl.CollisionObject → str]
        """
        fcl_objects = {}
        id_from_obj = {}

        # --- dynamic: agents ---
        for aid, ag in agents.items():
            obj = self._make_agent_obj(ag)
            fcl_objects[obj] = None
            id_from_obj[obj] = aid

        # --- static: obstacles ---
        for oid, obs in obstacles.items():
            obj = self._make_obstacle_obj(obs)
            fcl_objects[obj] = None
            id_from_obj[obj] = oid

        return fcl_objects, id_from_obj

    # ------------------------------------- GEOMETRY: Agent -------------------------------------
    
    def _make_agent_obj(self, ag):
        L = ag.agent_config.length
        W = ag.agent_config.width
        H = ag.agent_config.height


        if L <= 0 or W <= 0 or H <= 0:
            print("[FCL ERROR] Invalid agent dimensions:", L, W, H)

        x = ag.state.x
        y = ag.state.y
        psi = ag.state.psi

        pos = [x, y, 0.0]
        q = [np.cos(psi / 2), 0, 0, np.sin(psi / 2)]

        geom = fcl.Box(L, W, H)
        tf = fcl.Transform(q, pos)
        return fcl.CollisionObject(geom, tf)

    # ------------------------------------- GEOMETRY: Obstacle -------------------------------------

    def _make_obstacle_obj(self, obs):
        L = obs.config.length
        W = obs.config.width
        H = obs.config.height

        if L <= 0 or W <= 0 or H <= 0:
            print("[FCL ERROR] Invalid obstacle dimensions:", L, W, H)

        x = obs.state.x
        y = obs.state.y
        psi = obs.state.psi

        pos = [x, y, 0.0]
        q = [np.cos(psi / 2), 0, 0, np.sin(psi / 2)]

        geom = fcl.Box(L, W, H)
        tf = fcl.Transform(q, pos)
        return fcl.CollisionObject(geom, tf)
    
def frodo_collision_example():
    collision_checker = CollisionChecker()
    collision_checker.run_from_yaml()
    collision_checker.dump_collisions_to_yaml()

def simulatio_collision_example():
    ...


if __name__ == "__main__":
    simulatio_collision_example()    
