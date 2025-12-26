import numpy as np
import fcl
from master_thesis.containers.general_containers.agent_container import FRODOAgentContainer
from master_thesis.containers.general_containers.local_world_container import LocalWorldContainer
from master_thesis.containers.general_containers.environment_container import EnvironmentContainer
from master_thesis.containers.general_containers.obstacle_container import ObstacleContainer
from master_thesis.general.general_obstacle import GeneralObstacle
# import meshcat.transformations as tf

class AgentCollisionChecker():

    def __init__(self, agent_container: FRODOAgentContainer, lwr_container: LocalWorldContainer):
        self.lwr_config: LocalWorldContainer = lwr_container
        self.agent_config: FRODOAgentContainer = agent_container
        self.collisions_list = [] # initialize dynamic collison list
        self.initialize_collision_manager(lwr_container, agent_container)

    def check_agent_state(self):
        ...

    def check_env_state(self):
        ...

    def initialize_collision_manager(self, lwr_container, agent_container):
        self.initialize_env_manager(lwr_container)
        self.initialize_agent_manager(agent_container)

    def initialize_agent_manager(self, agent_container):
        # py-fcl does not expose the objects in a manager for update, therefore they must be accesible here
        self.agent_objs = self.create_agent_objects(agent_container)

        self.agent_manager = self.create_collision_manager(self.agent_objs)


    def initialize_env_manager(self, lwr_container: LocalWorldContainer):
        if not isinstance(lwr_container, LocalWorldContainer):
            raise TypeError('Did not pass valid local world container, argument of type: ', type(lwr_container))
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
        for obstacle in self.lwr_config.state.obstacles.values():
            _obs = self.create_env_collision_object(obstacle)
            obstacle_list.append(_obs)
        return obstacle_list
    
    def create_agent_objects(self, agent_container: FRODOAgentContainer):
        """
        Create the initial FCL collision object for the FRODO agent.
        The agent is initialized at state and its transform
        will be updated later inside check_state().
        """

        obj = self.create_collision_box(container= agent_container)
        return [obj]
    
    def create_env_collision_object(self, obstacle_container: ObstacleContainer):
        if obstacle_container.shape == "box":
            _obs = self.create_collision_box(container=obstacle_container)
        else:
            raise ValueError
        return _obs

    @staticmethod
    def create_collision_box(container : FRODOAgentContainer | ObstacleContainer):
        # FCL box expects (x_size, y_size, z_size)
        geometry = fcl.Box(container.length, container.width, container.height)

        # position
        pos = [container.x, container.y, 0.0]

        # default rotation: yaw = state.psi
        yaw = container.psi
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

        q = [np.cos(state.psi / 2), 0, 0, np.sin(state.psi / 2)]
        pos = [state.x, state.y, 0.0]

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

    def check_all(self):
        collisions = {aid: [] for aid in self.agent_objs.keys()}

        req = fcl.CollisionRequest(num_max_contacts=1, enable_contact=False)
        data = fcl.CollisionData(request=req)

        def cb(o1, o2, data):
            a = self.obj_to_id.get(o1)
            b = self.obj_to_id.get(o2)
            if a and b and a != b:
                collisions[a].append(b)
                collisions[b].append(a)
            return False

        self.manager.collide(self.manager, data, cb)
        return collisions