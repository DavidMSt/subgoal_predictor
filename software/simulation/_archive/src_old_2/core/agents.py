import extensions.simulation.src.core.environment as environment
import extensions.simulation.src.core.dynamics as dynamics
import extensions.simulation.src.core.spaces as spaces


# TODO: Make the agent group
class AgentGroup(environment.ObjectGroup):
    ...


class Agent(environment.Object):
    agent_id: str
    agent_group: AgentGroup

    def __init__(self, agent_id: str, env: environment.Environment = None,
                 space: spaces.Space = None, *args, **kwargs):
        super().__init__(object_id=agent_id, env=env, group=None, space=space, *args, **kwargs)

        self.collision.settings.check = True
        self.collision.settings.collidable = True

        self.agent_id = agent_id

    def _getParameters(self):
        params = super()._getParameters()
        params['agent_id'] = self.agent_id
        return params

    def _onAdd_callback(self):
        super()._onAdd_callback()
        self.env.addAgent(self)


class DynamicAgent(Agent, dynamics.DynamicObject):

    def __init__(self, agent_id: str, env: environment.Environment = None, space: spaces.Space = None,
                 *args, **kwargs):
        super().__init__(env=env, space=space, agent_id=agent_id, *args, **kwargs)
