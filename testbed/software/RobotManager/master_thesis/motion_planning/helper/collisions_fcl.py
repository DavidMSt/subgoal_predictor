import numpy as np
import yaml
import fcl
import argparse
# import meshcat.transformations as tf

class CollisionChecker():
    # _env: dict # environment in which agent is
    # _plan: dict # plan of configurations we want to check for collisions

    def __init__(self, env):
        self.env = env  # Ensure _env is always defined
        self.collisions_list = [] # initialize dynamic collison list

    def run_from_yaml(self):
        # load data from yaml
        self.args = self.parse_arguments()
        # extract env and configuration plan
        env, plan = self.load_data()
        # initialize the environment
        self.initialize_env(env)
        # set configuration plan to be checke
        self.set_plan(plan)
        # run the collision checking for each state of the plan
        self.broadphase_collision_checking(self.states)

    def set_plan(self, plan):
        # self._plan = plan
        self.states = plan["plan"]["states"]
    
    def set_dimensions(self, L, W= None, H= None):
        self.dimensions = {
            "L": L,
            "W": W,
            "H": H
        }

    def initialize_env(self, env= None):
        self.env = env
        # Defensive programming: check for 'obstacles' attribute
        if not hasattr(env, "obstacles"):
            raise AttributeError("Provided env has no 'obstacles' attribute")
        obstacle_list = self.create_environment_objects()
        self.env_manager = self.create_collision_manager(obstacle_list)

    @staticmethod
    def parse_arguments():
        parser = argparse.ArgumentParser()
        parser.add_argument('env', help='input YAML file with environment')
        parser.add_argument('plan', help='input YAML file with plan')
        parser.add_argument('output', help='output yaml-file')
        args = parser.parse_args()
        return args
    
    def load_data(self):
        # load environment
        with open(self.args.env, "r") as stream:
            env = yaml.safe_load(stream)
        # load plan
        with open(self.args.plan, "r") as stream:
            plan = yaml.safe_load(stream)
        return env, plan
    
    def check_state(self, state):
        """Check a single configuration for collision"""
        req = fcl.CollisionRequest(num_max_contacts=1, enable_contact=False)
        data = fcl.CollisionData(request=req)
        agent_objs = self.create_agent_objects(state)
        agent_manager = self.create_collision_manager(agent_objs)
        agent_manager.collide(self.env_manager, data, fcl.defaultCollisionCallback)
        return data.result.is_collision
    
    def check_state_ompl(self, state):
        x = state.getX()
        y = state.getY()
        theta = state.getYaw()
        config = [x, y, theta]


        valid = self.check_state(config)

        return not valid # ompl expects collision as return here

    def check_states(self, states):
        """Check multiple configurations"""
        return [self.check_state(s) for s in states]

    def broadphase_collision_checking(self, states):
        self.collisions_list = [self.check_state(state) for state in states]

    def create_agent_objects(self, state):
        objs = self.create_objects_frodo(state)

        return objs

    def create_environment_objects(self):
        obstacle_list = []
        for obstacle in self.env.obstacles:
            _obs = self.create_env_collision_object(obstacle)
            obstacle_list.append(_obs)
        return obstacle_list
    
    def create_env_collision_object(self, obstacle):
        if obstacle["type"] == "box":
            _obs = self.create_collision_box(obstacle["pos"], obstacle["size"])
        elif obstacle["type"] == "cylinder":
            _obs = self.create_collision_cylinder(obstacle["pos"], obstacle["q"], obstacle["r"], obstacle["lz"])
        else:
            raise ValueError
        return _obs
  

    def create_objects_frodo(self, state):
        x, y, theta = state

        # Use .get to avoid KeyError if values are missing
        L = self.dimensions.get("L")
        W = self.dimensions.get("W")
        H = self.dimensions.get("H")

        pos = [x, y, 0]
        q = [np.cos(theta / 2), 0, 0, np.sin(theta / 2)]  # Z-rotation quaternion

        obj = self.create_collision_box(pos, [L, W, H], q)
        objs = [obj]
        return objs

    @staticmethod
    def create_collision_box(pos, size, q = None):
        geometry = fcl.Box(*size)
        if q:
            transformation = fcl.Transform(q, pos)
        else: 
            transformation = fcl.Transform(pos)
        obj = fcl.CollisionObject(geometry, transformation)
        return obj

    @staticmethod
    def create_collision_cylinder(pos, q, radius, lz):
        geometry = fcl.Cylinder(radius, lz)
        transformation = fcl.Transform(q, pos)
        obj = fcl.CollisionObject(geometry, transformation)
        return obj

    @staticmethod
    def create_collision_manager(objects: list):
        manager = fcl.DynamicAABBTreeCollisionManager()
        manager.registerObjects(objects)
        manager.setup()
        return manager

    def dump_collisions_to_yaml(self):
        """Dump the plan to a yaml file with the given target path"""
        print(self.args.output)

        collision_content = {
            'collisions': self.collisions_list
        }

        with open(self.args.output, 'w') as file:
            yaml.dump(collision_content, file, default_flow_style=False)


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
