# third party
import math
import time
import copy
import numpy as np
from dataclasses import dataclass, field
import logging

# bilbolab
from applications.FRODO.simulation.frodo_simulation import FRODO_Simulation,  FRODO_ENVIRONMENT_ACTIONS, FRODO_SimulationObject
from extensions.simulation.src.objects.frodo.frodo import FRODO_DynamicAgent
from extensions.simulation.src.core.environment import BASE_ENVIRONMENT_ACTIONS
from extensions.cli.cli import CommandSet, Command, CommandArgument
# from extensions.simulation.src.objects.frodo.frodo import FRODO_State
import extensions.simulation.src.core as core
from core.utils.logging_utils import Logger
from master_thesis.containers.general_containers.agent_container import FRODOAgentContainer, FRODO_Agent_Config, FRODO_AgentState
from master_thesis.containers.general_containers.environment_container import EnvironmentContainer
from master_thesis.containers.general_containers.local_world_container import LocalWorldContainer


class FRODOGeneralAgent(FRODO_DynamicAgent, FRODO_SimulationObject):
    lwr_cont: LocalWorldContainer | None

    """
    Lightweight general agent:
    - uses FRODO_DynamicAgent for motion
    - uses FRODO_SimulationObject for world representation
    - optional PhaseRunner for scripted inputs
    """

    def __init__(
    self,
    agent_id: str,
    Ts=0.1, # TODO: this could probably be removed anyway, since Ts could also be received by env updates?
    start_config: tuple[float, float, float] = (0.0, 0.0, 0.0),
    color: tuple[float, float, float] = (1.0, 1.0, 1.0),
    log_level: str = 'INFO',
    ):
        agent_config = FRODO_Agent_Config(color = color, Ts= Ts)

        # ─────────────────────────────────────────────
        # CONTAINER + LOCAL WORLD REPRESENTATION
        # ─────────────────────────────────────────────
        self.container = FRODOAgentContainer(
            agent_id= agent_id,
            config=agent_config,
            state = FRODO_AgentState(x = start_config[0], y = start_config[1], psi = start_config[2], v = 0.0, psi_dot = 0.0)
        )
        # self.lwr = LocalWorldRepresentation(self_agent=self.container)
        # ─────────────────────────────────────────────

        self.agent_id = agent_id
        self.color = agent_config.color
        self.size = getattr(agent_config, "size", 0.2)
        self.logger = Logger(agent_id, log_level)

        super().__init__(agent_id=agent_id, Ts=Ts)

        self.cli = FRODO_GeneralAgent_CommandSet(self)
        self.setup_scheduling()

        # Apply initial configuration
        x0, y0, psi0 = start_config
        self.state.x = float(x0)
        self.state.y = float(y0)
        self.state.psi = float(psi0)

        # Local world representation, will be initialized and updated, when agent is added to environment
        self.lwr_cont = None



    def setup_scheduling(self):
        
        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.COMMUNICATION].addAction(self.action_frodo_communication)

        # Attach the update function for the agent containers
        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.OUTPUT].addAction(self._container_update_function)


    def action_frodo_communication(self):
        # TODO: dummy function for all communication from the FRODO class outwards
        ...

    def _get_state(self):
        return self.state

    # ----------------------------------------------------------------------

    def _container_update_function(self):
        st = self.container.state
        st.x = self.state.x
        st.y = self.state.y
        st.psi = self.state.psi

    # ----------------------------------------------------------------------
    def output(self, env):
        """Populate configuration_global for collision detection."""
        # Update the local configuration from the current state
        if hasattr(self, '_configuration') and self._configuration is not None:
            self._configuration['pos'] = [self.state.x, self.state.y]
            if hasattr(self._configuration, 'ori') or 'ori' in dir(self._configuration):
                self._configuration['ori'] = [self.state.psi]

class FRODO_GeneralAgent_CommandSet(CommandSet):
    def __init__(self, agent: FRODOGeneralAgent):
        super().__init__(name=agent.agent_id)
        self.agent = agent

        # ---- Command: set state -----------------------------------------
        cmd_set_state = Command(
            name='set_state',
            description='Set agent pose directly',
            arguments=[
                CommandArgument('x', type=float, optional=True, default=None),
                CommandArgument('y', type=float, optional=True, default=None),
                CommandArgument('psi', type=float, optional=True, default=None),
            ],
            function=self._set_state,
            allow_positionals=True
        )

        # ---- Command: set input -----------------------------------------
        cmd_set_input = Command(
            name='set_input',
            description='Set velocity inputs (v, psi_dot)',
            arguments=[
                CommandArgument('v', type=float),
                CommandArgument('psi_dot', type=float),
            ],
            function=self._set_input,
            allow_positionals=True
        )

        # ---- Command: switch phase --------------------------------------
        cmd_phase = Command(
            name='phase',
            description='Switch to existing phase by name',
            arguments=[
                CommandArgument('name', type=str),
            ],
            function=self._change_phase,
            allow_positionals=True
        )

        self.addCommand(cmd_set_state)
        self.addCommand(cmd_set_input)
        self.addCommand(cmd_phase)

    # ------------------------------------------------------------------
    def _set_state(self, x=None, y=None, psi=None):
        if x is not None:
            self.agent.state.x = x
        if y is not None:
            self.agent.state.y = y
        if psi is not None:
            self.agent.state.psi = psi

    # ------------------------------------------------------------------
    def _set_input(self, v, psi_dot):
        self.agent.input.v = v
        self.agent.input.psi_dot = psi_dot

    # ------------------------------------------------------------------
    def _change_phase(self, name):
        self.agent.activate_phase(name)

if __name__ == '__main__':
    ...

    # sim = FRODO_Simulation()
    # sim.init()

    # cfg = FRODO_Agent_Config(
    #     color = (1, 0, 0), 
    # )

    # agent = FRODOGeneralAgent(agent_id = 'frodo01', start_config= [0.0,0.0,0.0])

    # # sim.new_agent(agent_id='vfrodo1', fov_deg=100, vision_radius=1.5)
    # sim.add_agent(agent)

    # sim.start()

    # while True:
    #     time.sleep(10)