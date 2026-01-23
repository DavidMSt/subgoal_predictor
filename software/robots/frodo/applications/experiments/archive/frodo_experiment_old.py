from __future__ import annotations

import dataclasses
import enum
import threading
import time

import numpy as np

from applications.FRODO.agent_manager import FRODO_AgentManager
from applications.FRODO.algorithm_manager import FRODO_AlgorithmManager
from applications.FRODO.navigation.multi_agent_navigator import MultiAgentNavigator, Move, NavigatorPlan
from applications.FRODO.navigation.navigator import CoordinatedMoveTo
from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.events import Event, event_definition, EventFlag, wait_for_events, OR, TIMEOUT
from core.utils.files import fileExists
from core.utils.logging_utils import Logger
from core.utils.time import IntervalTimer


@dataclasses.dataclass(kw_only=True)
class ExperimentAction:
    id: str
    description: str
    time: float  # When this action should be executed, relative to the start of the experiment
    action: str  # The action to be executed
    parameters: dict[str, str | float | int] | None = None


@dataclasses.dataclass(kw_only=True)
class AddSimulatedAgent(ExperimentAction):
    action: str = "add_simulated_agent"
    agent_id: str


@dataclasses.dataclass(kw_only=True)
class RemoveSimulatedAgent(ExperimentAction):
    action: str = "remove_simulated_agent"
    agent_id: str


@dataclasses.dataclass(kw_only=True)
class AddSimulatedStatic(ExperimentAction):
    action: str = "add_simulated_static"
    static_id: str


@dataclasses.dataclass(kw_only=True)
class RemoveSimulatedStatic(ExperimentAction):
    action: str = "remove_simulated_static"
    static_id: str


@dataclasses.dataclass(kw_only=True)
class SetState(ExperimentAction):
    action: str = "set_state"
    object_id: str
    state: dict[str, float | int]


@dataclasses.dataclass(kw_only=True)
class RestartAlgorithm(ExperimentAction):
    action: str = "restart_algorithm"


@dataclasses.dataclass
class FRODO_Experiment_Definition:
    id: str
    description: str

    robots: list[str]
    statics: list[str]

    virtual_robots: list[str]
    virtual_statics: list[str]

    interactive_agents: list[str]  # TODO: Assign joysticks to agents

    initial_states: dict[str, list[float]]
    movement_plan: str  # File of the movement yaml file
    algorithm_settings: dict[str, dict[str, str | float | int]]

    Ts: float

    length: float | None = None

    actions: list[ExperimentAction] | None = None

    def to_yaml(self, file: str):
        ...

    @classmethod
    def from_yaml(cls, file: str) -> FRODO_Experiment_Definition:
        ...


@dataclasses.dataclass
class FRODO_Experiment_Result:
    experiment_id: str
    time: float

    def to_json(self, file: str):
        ...

    @classmethod
    def from_json(cls, file: str) -> FRODO_Experiment_Result:
        ...


class FRODO_Experiment_Status(enum.StrEnum):
    NOT_STARTED = "not_started"
    RUNNING = "running"
    FINISHED = "finished"
    ERROR = "error"


@dataclasses.dataclass
class FRODO_Experiment_Events:
    started: Event = Event(copy_data_on_set=False)
    finished: Event = Event(copy_data_on_set=False)
    error: Event = Event(copy_data_on_set=False)


class FRODO_Experiment:
    definition: FRODO_Experiment_Definition
    result: FRODO_Experiment_Result | None = None

    _start_time: float = 0.0
    _exit: bool = False
    state: FRODO_Experiment_Status = FRODO_Experiment_Status.NOT_STARTED

    _thread: threading.Thread
    _timer: IntervalTimer
    _step: int = 0

    _experiment_plan: NavigatorPlan | None = None
    _experiment_plan_finished: bool = False
    _experiment_plan_error: bool = False

    _experiment_actions: list[ExperimentAction] | None = None
    agent_manager: FRODO_AgentManager
    navigator: MultiAgentNavigator

    # === INIT =========================================================================================================
    def __init__(self,
                 definition: FRODO_Experiment_Definition,
                 agent_manager: FRODO_AgentManager,
                 navigator: MultiAgentNavigator,
                 algorithm_manager: FRODO_AlgorithmManager
                 ):

        self.definition = definition
        self.logger = Logger(f'Experiment {self.definition.id}', 'DEBUG')
        self.events = FRODO_Experiment_Events()

        self.agent_manager = agent_manager
        self.navigator = navigator
        self.algorithm_manager = algorithm_manager

        self.agent_manager.events.error.on()

        self._experiment_actions = self.definition.actions

        for action in self._experiment_actions:
            action.finished = False

        self._thread = threading.Thread(target=self._task)
        self._timer = IntervalTimer(self.definition.Ts, raise_race_condition_error=False)

    # === PROPERTIES ===================================================================================================
    @property
    def step(self):
        return self._step

    # === METHODS ======================================================================================================

    # ------------------------------------------------------------------------------------------------------------------
    def check_preconditions(self) -> bool:

        self.logger.info("Checking preconditions ...")
        self.logger.info(f"Real robots: {self.definition.robots}")
        # 1. Check if all real robots are available
        for real_robot_id in self.definition.robots:
            if real_robot_id not in self.agent_manager.real_agents:
                self.logger.error(f"❌ Real robot \"{real_robot_id}\" is not available.")
                return False

        # TODO: Ping the robots
        self.logger.info("✅ All real robots are available")

        # 2. Check if there are additional robots that are not in the definition
        for robot_id in self.agent_manager.real_agents:
            if robot_id not in self.definition.robots:
                self.logger.error(
                    f"❌ Robot {robot_id} is in the testbed, but is not part of the experiment definition.")
                return False

        # 3. Check if all real statics are available
        self.logger.info(f"Real Statics: {self.definition.statics}")
        for real_static_id in self.definition.statics:
            if real_static_id not in self.agent_manager.real_statics:
                self.logger.error(f"❌ Real static \"{real_static_id}\" is not available.")
                return False
        self.logger.info(f"✅ All real statics are available")

        # 4. Check if there are additional statics that are not in the definition
        for static_id in self.agent_manager.real_statics:
            if static_id not in self.definition.statics:
                self.logger.error(
                    f"❌ Static {static_id} is in the testbed, but is not part of the experiment definition.")
                return False

        # 5. Check if all virtual robots are available
        for virtual_robot_id in self.definition.virtual_robots:
            if virtual_robot_id not in self.agent_manager.simulated_agents:
                # If it's not there, add it
                self.agent_manager.add_virtual_agent(virtual_robot_id)
                self.logger.info(f"Added virtual robot {virtual_robot_id}")

        # 6. Check if there are agents in the simulation that are not in the definition
        for agent_id in self.agent_manager.simulated_agents:
            if agent_id not in self.definition.virtual_robots:
                self.agent_manager.remove_simulated_agent(agent_id)
                self.logger.info(f"Removed simulated agent {agent_id}")

        # 7. Check if all virtual statics are available
        for virtual_static_id in self.definition.virtual_statics:
            if virtual_static_id not in self.agent_manager.simulated_statics:
                # If it's not there, add it
                self.agent_manager.add_virtual_static(virtual_static_id)
                self.logger.info(f"Added virtual static {virtual_static_id}")

        # 8. Check if there are statics in the simulation that are not in the definition
        for static_id in self.agent_manager.simulated_statics:
            if static_id not in self.definition.virtual_statics:
                self.agent_manager.remove_simulated_static(static_id)
                self.logger.info(f"Removed simulated static {static_id}")

        self.logger.info("✅ All preconditions met")
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def set_initial_states(self) -> bool:
        self.logger.info("Setting initial states ...")
        # 1. Set the initial states of the simulated agents since that's easy
        for simulated_agent in self.agent_manager.simulated_agents.values():
            if simulated_agent.id in self.definition.initial_states:
                simulated_agent.agent.set_state(x=self.definition.initial_states[simulated_agent.id][0],
                                                y=self.definition.initial_states[simulated_agent.id][1],
                                                psi=self.definition.initial_states[simulated_agent.id][2])
                simulated_agent.agent.input.v = 0
                simulated_agent.agent.input.psi_dot = 0
                self.logger.info(f"Set initial state for simulated agent {simulated_agent.id}")
            else:
                self.logger.warning(f"No initial state for simulated agent {simulated_agent.id}")

        # 2. Set the initial states of the simulated statics
        for simulated_static in self.agent_manager.simulated_statics.values():
            if simulated_static.id in self.definition.initial_states:
                simulated_static.static.set_state(x=self.definition.initial_states[simulated_static.id][0],
                                                  y=self.definition.initial_states[simulated_static.id][1],
                                                  psi=self.definition.initial_states[simulated_static.id][2])
                self.logger.info(f"Set initial state for simulated static {simulated_static.id}")

        # 3. Check the initial states of the real statics. This is a bit tricky, since they cannot move on their own

        # TODO
        self.logger.warning(f"Initial state check for real statics not implemented yet")

        # 4. Set the initial states of the real robots. For this, build a plan in the navigator
        move_actions = []
        for robot_id in self.definition.robots:
            if robot_id not in self.definition.initial_states:
                self.logger.warning(f"No initial state for real robot {robot_id}")
                continue

            action = Move(
                id=f'initial_move_{robot_id}',
                agent_id=robot_id,
                element=CoordinatedMoveTo(
                    x=self.definition.initial_states[robot_id][0],
                    y=self.definition.initial_states[robot_id][1],
                    psi_end=self.definition.initial_states[robot_id][2],
                    final_heading_tolerance=np.deg2rad(5)  # Relax the tolerance for the initial move
                ),
                blocking=True
                # For now do blocking here, so that the robots move to their initial positions one after the other
            )
            move_actions.append(action)

        plan = NavigatorPlan(
            id='initial_move',
            actions=move_actions
        )

        self.navigator.load_plan(plan)
        self.logger.info("Initial move plan created")
        self.navigator.run_current_plan()

        data, trace = wait_for_events(
            OR(
                plan.events.finished,
                plan.events.error
            ),
            timeout=60  # Set the timeout to 60 seconds for the initial moves
        )

        if data is TIMEOUT:
            self.logger.error("⏱️Initial move timed out")
            return False

        if trace.caused_by(plan.events.error):
            self.logger.error("❌Initial move failed")
            return False

        if trace.caused_by(plan.events.finished):
            self.logger.info("✅ Initial move finished")
            return True
        else:
            self.logger.error("❌Initial move did not finish due to an unknown error")
            return False

    # ------------------------------------------------------------------------------------------------------------------
    def run(self):
        if self.state != FRODO_Experiment_Status.NOT_STARTED:
            self.logger.warning("Experiment already running. Exiting.")
            return

        self.logger.info(f"Starting experiment {self.definition.id}")
        self.logger.info(f"Description: {self.definition.description}")
        self.logger.info(f"Robots: {self.definition.robots}")
        self.logger.info(f"Virtual robots: {self.definition.virtual_robots}")
        self.logger.info(f"Virtual statics: {self.definition.virtual_statics}")
        self.logger.info(f"Interactive agents: {self.definition.interactive_agents}")
        self.logger.info(f"Length: {self.definition.length}")

        # Set the experiment status
        self.state = FRODO_Experiment_Status.RUNNING

        # Set the start time
        self._start_time = time.monotonic()
        self._step = 0

        # Run the thread
        self._thread = threading.Thread(target=self._task)
        self._thread.start()
        self.logger.info("Experiment started")

    # ------------------------------------------------------------------------------------------------------------------
    def stop(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def save(self, folder: str):
        ...

    # === PRIVATE METHODS ==============================================================================================
    def _get_experiment_time(self) -> float:
        return time.monotonic() - self._start_time

    # ------------------------------------------------------------------------------------------------------------------
    def _task(self):

        # 1. Check the preconditions
        result = self.check_preconditions()

        if not result:
            self.events.error.set()
            return

        # 2. Set the initial states
        result = self.set_initial_states()

        if not result:
            self.events.error.set()
            return

        # 3. Set the experiment navigation plan
        result = self._set_experiment_navigation_plan()
        if not result:
            self.events.error.set()
            return

        # 4. Attach events of the plan
        self._experiment_plan.events.finished.on(self._on_experiment_plan_finished)
        self._experiment_plan.events.error.on(self._on_experiment_plan_error)

        self.navigator.run_current_plan()

        self._timer.reset()
        while not self._exit:
            self._update()
            self._step += 1
            self._timer.sleep_until_next()

    # ------------------------------------------------------------------------------------------------------------------
    def _update(self):

        # 1. Check if the experiment time has elapsed
        if self.definition.length is not None:
            if self._get_experiment_time() > self.definition.length:
                self.logger.info("Experiment time limit reached")
                self.logger.warning("Not implemented yet!")
                self._handle_experiment_time_elapsed()
                return
        else:
            # 2. Check if the experiment plan has finished
            if self._experiment_plan_finished:
                self.logger.info("Experiment plan finished")
                self._handle_experiment_plan_finished()
                return

        # 3. Check if any of the actions has to be called
        for action in self._experiment_actions:
            if action.finished:
                continue
            if self._get_experiment_time() >= action.time:
                self._execute_action(action)

        # 4. Log all data and events and errors and so on
        # TODO

    # ------------------------------------------------------------------------------------------------------------------
    def _set_experiment_navigation_plan(self) -> bool:

        # 1. Load the movement plan from file
        if not fileExists(self.definition.movement_plan):
            self.logger.error(f"Movement plan file '{self.definition.movement_plan}' does not exist.")
            return False

        self._experiment_plan = NavigatorPlan.from_yaml(self.definition.movement_plan)

        self.navigator.load_plan(self._experiment_plan, start=False)
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def _on_experiment_plan_finished(self, *args, **kwargs):
        self.logger.info("Experiment plan finished")
        self._experiment_plan_finished = True

    # ------------------------------------------------------------------------------------------------------------------
    def _on_experiment_plan_error(self, *args, **kwargs):
        self.logger.error("Experiment plan error")

    # ------------------------------------------------------------------------------------------------------------------
    def _execute_action(self, action: ExperimentAction):
        self.logger.info(f"Executing action {action.action}")

        match action.action:
            case 'add_simulated_agent':
                self.logger.info("Adding simulated agent")
            case 'add_simulated_static':
                self.logger.info("Adding simulated static")
            case 'remove_simulated_agent':
                self.logger.info("Removing simulated agent")
            case 'remove_simulated_static':
                self.logger.info("Removing simulated static")
            case 'set_state':
                self.logger.info("Setting state")
            case 'restart_algorithm':
                self.logger.info("Restarting algorithm")
            case _:
                self.logger.error(f"Action {action.action} not implemented")

        action.finished = True
        self.logger.warning("Not implemented yet!")


# ======================================================================================================================
@callback_definition
class FRODO_Experiment_Handler_Callbacks:
    started: CallbackContainer
    finished: CallbackContainer
    error: CallbackContainer


@event_definition
class FRODO_Experiment_Handler_Events:
    started: Event = Event(copy_data_on_set=False, flags=EventFlag('id', str))
    finished: Event = Event(copy_data_on_set=False, flags=EventFlag('id', str))
    error: Event = Event(copy_data_on_set=False, flags=EventFlag('id', str))


class FRODO_Experiment_Handler_State(enum.StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"


class FRODO_Experiment_Handler:
    callbacks: FRODO_Experiment_Handler_Callbacks
    events: FRODO_Experiment_Handler_Events

    agent_manager: FRODO_AgentManager
    navigator: MultiAgentNavigator

    current_experiment: FRODO_Experiment | None = None
    state: FRODO_Experiment_Handler_State = FRODO_Experiment_Handler_State.IDLE

    # === INIT =========================================================================================================
    def __init__(self,
                 agent_manager: FRODO_AgentManager,
                 navigator: MultiAgentNavigator,
                 ):
        self.logger = Logger('FRODO Experiment Handler', 'DEBUG')
        self.callbacks = FRODO_Experiment_Handler_Callbacks()
        self.events = FRODO_Experiment_Handler_Events()

    # ------------------------------------------------------------------------------------------------------------------
    def load_experiment_from_file(self, file: str):
        if not fileExists(file):
            self.logger.error(f"File '{file}' does not exist.")
            return

    # ------------------------------------------------------------------------------------------------------------------
    def load_experiment(self, experiment_definition: FRODO_Experiment_Definition):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def run_experiment(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def stop_experiment(self):
        ...
