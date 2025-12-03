from extensions.cli.cli import CommandSet, Command, CommandArgument

from master_thesis.general.general_simulation import FRODO_general_Simulation, FrodoGeneralEnvironment, SIMULATED_AGENTS, SIMULATED_STATICS
from master_thesis.universal.universal_agent import FRODOUniversalAgent
from master_thesis.motion_planning.mp_simulation import MPSimulationModule
from master_thesis.task_assignment.task_simulation import AssignmentSimulationModule

class FRODO_General_CommandSet(CommandSet):
    def __init__(self, sim: "FRODO_general_Simulation"):
        super().__init__(name='simulation')
        self.sim = sim

        # ------------------------------------------------------------------
        # LIST
        # ------------------------------------------------------------------
        self.addCommand(Command(
            name='list',
            description='List all agents and statics',
            arguments=[],
            function=lambda: self.sim.logger.info(
                f"Agents: {list(SIMULATED_AGENTS.keys())}\nStatics: {list(SIMULATED_STATICS.keys())}"
            )
        ))

        # ------------------------------------------------------------------
        # ADD AGENT  (GeneralAgent only)
        # ------------------------------------------------------------------
        self.addCommand(Command(
            name='add_agent',
            description='Add a general agent',
            arguments=[
                CommandArgument('agent_id', type=str, description='Agent ID'),
                CommandArgument('x', type=float, description='start x', optional=True, default=0.0),
                CommandArgument('y', type=float, description='start y', optional=True, default=0.0),
                CommandArgument('psi', type=float, description='start orientation', optional=True, default=0.0),
                CommandArgument('color', type=list, description='RGB color', optional=True, default=None),
            ],
            function=self._add_general_agent
        ))

        # ------------------------------------------------------------------
        # REMOVE AGENT
        # ------------------------------------------------------------------
        self.addCommand(Command(
            name='remove_agent',
            description='Remove a general agent',
            allow_positionals=True,
            arguments=[
                CommandArgument('agent', type=str, description='Agent ID'),
            ],
            function=self.sim.remove_agent
        ))

        # ------------------------------------------------------------------
        # ADD STATIC
        # ------------------------------------------------------------------
        self.addCommand(Command(
            name='add_static',
            description='Add a static object',
            arguments=[
                CommandArgument('static_id', type=str),
                CommandArgument('x', type=float, optional=True, default=None),
                CommandArgument('y', type=float, optional=True, default=None),
                CommandArgument('psi', type=float, optional=True, default=None),
                CommandArgument('size', type=float, optional=True, default=0.2),
            ],
            function=self.sim.new_static
        ))

    # === private ---------------------------------------------------------
    def _add_general_agent(self, agent_id, x=0.0, y=0.0, psi=0.0, color=None):
        return self.sim.new_agent(
            agent_id=agent_id,
            start_config=(x, y, psi),
            color=color
        )

class FRODO_universal_Simulation(FRODO_general_Simulation):
    cli: FRODO_General_CommandSet | None = None

    def __init__(self, Ts=0.1, limits=((-3,3),(-3,3)), env=FrodoGeneralEnvironment):
        super().__init__(Ts=Ts, limits=limits, env=env)
        self.mpi = MPSimulationModule(self.agents, self.logger)
        self.asi = AssignmentSimulationModule(env = env, logger=  self.logger, new_agent_fun= FRODOUniversalAgent)
        self.cli = FRODO_General_CommandSet(self)

    def new_agent(self, agent_id, start_config=(0.0, 0.0, 0.0), **kwargs):
        agent = FRODOUniversalAgent(
            env_config=self.environment.environment_container,
            agent_id=agent_id,
            Ts=self.Ts,
            start_config=start_config,
            **kwargs
        )
        self.add_agent(agent)
        return agent

if __name__ == "__main__":
    ...
