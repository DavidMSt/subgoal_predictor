from general.general_simulation import FRODO_general_Simulation, FrodoGeneralEnvironment
from universal.universal_agent import UniversalAgent
from motion_planning.mp_simulation import MPSimulationModule
from task_assignment.task_simulation import AssignmentSimulationModule

class UniversalSimulation(FRODO_general_Simulation):
    def __init__(self, Ts=0.1, limits=((-3,3),(-3,3)), env=FrodoGeneralEnvironment):
        super().__init__(Ts=Ts, limits=limits, env=env)
        self.mpi = MPSimulationModule(self.agents, self.logger)
        self.asi = AssignmentSimulationModule(env = env, logger=  self.logger, add_virtual_agent= UniversalAgent)

    def new_agent(self, agent_id, start_config, **kwargs):
        agent = UniversalAgent(
            env=self.environment,
            agent_id=agent_id,
            Ts=self.Ts,
            start_config=start_config,
            **kwargs
        )
        self.add_agent(agent)
        return agent

if __name__ == "__main__":
    ...
