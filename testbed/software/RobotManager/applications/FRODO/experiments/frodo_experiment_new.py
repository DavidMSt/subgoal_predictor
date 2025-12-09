from __future__ import annotations

import abc
import dataclasses
import enum
import threading
import time
from typing import Any

from applications.FRODO.agent_manager import FRODO_AgentManager, AgentManager_Sample, AgentContainer
from applications.FRODO.algorithm.algorithm import AlgorithmAgentInput, AlgorithmAgentMeasurement
from applications.FRODO.algorithm.algorithm_manager import FRODO_AlgorithmManager, AlgorithmAgentUpdateData

from applications.FRODO.algorithm.algorithm_manager import AlgorithmAgentContainer
from applications.FRODO.navigation.multi_agent_navigator import MultiAgentNavigator
from core.utils.callbacks import Callback
from core.utils.events import event_definition, Event, SubscriberListener, EventContainer, EventFlag
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger
from core.utils.time import IntervalTimer
from extensions.cli.cli import CommandSet


# ======================================================================================================================
@event_definition
class ExperimentActionEvents:
    started: Event
    finished: Event
    timeout: Event
    error: Event


@dataclasses.dataclass(kw_only=True)
class ExperimentAction(abc.ABC):
    type: str
    id: str
    data: Any = None
    description: str | None = None
    after: str | None = None  # Specify the id of an action after which this action should be executed
    time: float | None = None  # Time in seconds after which the action should be executed (in the experiment time)

    timeout: float | None = None

    _experiment: FRODO_Experiment
    started: bool = False
    finished: bool = False

    def __post_init__(self):
        self.events = ExperimentActionEvents(self)
        if self.time is not None and self.after is not None:
            raise ValueError("Cannot specify both time and after for an ction.")

    def initialize(self, experiment: FRODO_Experiment):
        self._experiment = experiment

    @abc.abstractmethod
    def execute(self):
        self._on_started()

    def _on_started(self):
        self.started = True
        self.events.started.set()

    def _on_finished(self):
        self.finished = True
        self.events.finished.set(data=self.data)

    def _on_timeout(self):
        self.events.timeout.set()

    def _on_error(self):
        self.events.error.set()


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class AddSimulatedAgent(ExperimentAction):
    type: str = "add_simulated_agent"
    agent_id: str
    config: dict[str, Any]

    def execute(self):
        self._experiment.experiment_handler


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class RemoveSimulatedAgent(ExperimentAction):
    type: str = "remove_simulated_agent"
    agent_id: str


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class AddSimulatedStatic(ExperimentAction):
    type: str = "add_simulated_static"
    static_id: str
    config: dict[str, Any]


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class RemoveSimulatedStatic(ExperimentAction):
    type: str = "remove_simulated_static"
    static_id: str


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class SetState(ExperimentAction):
    type: str = "set_agent_state"
    object_id: str
    state: list


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class SetMarker(ExperimentAction):
    type: str = "set_marker"
    id: str
    value: str


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class StartAlgorithm(ExperimentAction):
    type: str = "start_algorithm"


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class StopAlgorithm(ExperimentAction):
    type: str = "stop_algorithm"


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class StartLogging(ExperimentAction):
    type: str = "start_logging"
    id: str


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class StopLogging(ExperimentAction):
    type: str = "stop_logging"
    id: str


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class Speak(ExperimentAction):
    type: str = "speak"
    text: str


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class RunPlan(ExperimentAction):
    type: str = "run_plan"
    plan: ...


# ----------------------------------------------------------------------------------------------------------------------

# ----------------------------------------------------------------------------------------------------------------------

# ----------------------------------------------------------------------------------------------------------------------


# === EXPERIMENT =======================================================================================================
@dataclasses.dataclass
class FRODO_Experiment_Definition:
    id: str
    description: str

    robots: list[str]
    statics: list[str]

    virtual_robots: list[str]
    virtual_statics: list[str]

    joystick_assignments: list[tuple[str, str]]

    initial_states: dict[str, list[float]]

    movement_plan: str  # File of the movement yaml file
    algorithm_settings: dict[str, dict[str, str | float | int]]

    length: float | None = None  # Length of the experiment in s
    actions: list[ExperimentAction] | None = None


@dataclasses.dataclass
class ActionContainer:
    action: ExperimentAction
    started: bool = False
    finished: bool = False
    handled: bool = False
    listeners: list[SubscriberListener] = dataclasses.field(default_factory=list)
    following_actions: dict[str, ActionContainer] = dataclasses.field(default_factory=list)


class FRODO_Experiment_Status(enum.StrEnum):
    NOT_STARTED = "not_started"
    RUNNING = "running"
    FINISHED = "finished"
    ERROR = "error"


@event_definition
class FRODO_Experiment_Events(EventContainer):
    action_started: Event = Event(copy_data_on_set=False, flags=[EventFlag('action_id', str)])
    finished: Event = Event(copy_data_on_set=False)
    error: Event = Event(copy_data_on_set=False)
    timeout: Event = Event(copy_data_on_set=False)


class FRODO_Experiment:
    definition: FRODO_Experiment_Definition
    actions: dict[str, ActionContainer] = dataclasses.field(default_factory=list)

    time: float = 0.0  # Internal time of the experiment
    time_absolut: float = 0.0  # Absolute time of the experiment
    timeout: float | None = None

    _step: int = 0
    _timer: IntervalTimer | None = None
    status: FRODO_Experiment_Status = FRODO_Experiment_Status.NOT_STARTED
    experiment_handler: FRODO_Experiment_Handler | None = None
    _thread: threading.Thread | None = None
    _exit: bool = False

    _start_time: float = 0.0

    # ------------------------------------------------------------------------------------------------------------------
    def __init__(self, definition: FRODO_Experiment_Definition):
        self.logger = Logger(f'Experiment {self.definition.id}', 'DEBUG')
        self._thread = None
        self._timer = IntervalTimer(interval=0.1, raise_race_condition_error=False)
        self.events = FRODO_Experiment_Events()
        self.definition = definition

        for action in actions:
            if action.id in self.actions:
                self.logger.error(f"Duplicate action ID {action.id}")
                continue

            self.actions[action.id] = ActionContainer(action=action)

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def experiment_time(self):
        return time.monotonic() - self._start_time

    # ------------------------------------------------------------------------------------------------------------------
    def initialize(self, experiment_handler: FRODO_Experiment_Handler):
        if self.status == FRODO_Experiment_Status.RUNNING:
            self.logger.error("Experiment is already running. Cannot initialize.")
            return
        self.experiment_handler = experiment_handler
        self.status = FRODO_Experiment_Status.NOT_STARTED
        self._thread = threading.Thread(target=self._task, daemon=True)
        self._exit = False
        self._step = 0

        for action in self.actions.values():
            action.action.initialize(self)
            if action.action.after is not None:
                self.actions[action.action.after].following_actions[action.action.id] = action

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        if self.status != FRODO_Experiment_Status.NOT_STARTED:
            self.logger.error("Experiment cannot be started.")
            return
        self.logger.info("Starting")
        self.status = FRODO_Experiment_Status.RUNNING
        self._thread.start()

    # ------------------------------------------------------------------------------------------------------------------
    def to_file(self, file: str):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def from_file(self, file: str):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def _task(self):
        self._timer.reset()
        self._start_time = time.monotonic()
        while not self._exit:
            self._update()
            self._timer.sleep_until_next()

    # ------------------------------------------------------------------------------------------------------------------
    def _update(self):

        for action_id, action_container in self.actions.items():
            if action_container.handled:
                continue

            # If the action is not started yet, and the action is time-dependent, not action-dependent, start it
            if not action_container.started and action_container.action.time is not None and self.experiment_time >= action_container.action.time:
                self._start_action(action_container)

            if action_container.finished:
                self._handle_action_finished(action_container)

        if all(action_container.handled for action_container in self.actions.values()):
            ...

        if self.timeout is not None and self.experiment_time >= self.timeout:
            self.status = FRODO_Experiment_Status.ERROR
            self._handle_experiment_timeout()
            self.events.timeout.set()

    # ------------------------------------------------------------------------------------------------------------------
    def _handle_action_finished(self, container: ActionContainer):

        for action_id, action_container in container.following_actions.items():
            self._start_action(action_container)

        container.handled = True

    # ------------------------------------------------------------------------------------------------------------------
    def _start_action(self, container: ActionContainer):

        # Attach the events
        listener = container.action.events.finished.on(
            callback=Callback(
                function=self._on_action_finished,
                discard_inputs=True,
                inputs={
                    'container': container
                }
            ),
            once=True
        )

        container.listeners.append(listener)

        listener = container.action.events.error.on(
            callback=Callback(
                function=self._on_action_error,
                discard_inputs=True,
                inputs={
                    'container': container
                }
            ),
            once=True
        )
        container.listeners.append(listener)

        listener = container.action.events.timeout.on(
            callback=Callback(
                function=self._on_action_timeout,
                discard_inputs=True,
                inputs={
                    'container': container
                }
            ),
            once=True
        )
        container.listeners.append(listener)

        # Start the action
        container.action.execute()

        self.events.action_started.set(flags={'action_id': container.action.id})
        self.logger.info(f"Started action {container.action.id}")

        if container.action.finished:
            self._handle_action_finished(container)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_action_finished(self, container: ActionContainer):
        self.logger.info(f"Action {container.action.id} finished")
        container.finished = True

    # ------------------------------------------------------------------------------------------------------------------
    def _on_action_error(self, container: ActionContainer):
        self.logger.error(f"Action {container.action.id} failed")

    # ------------------------------------------------------------------------------------------------------------------
    def _on_action_timeout(self, container: ActionContainer):
        self.logger.warning(f"Action {container.action.id} timed out")

    # ------------------------------------------------------------------------------------------------------------------
    def _handle_experiment_timeout(self):
        self.logger.error("Experiment timed out")
        self.status = FRODO_Experiment_Status.ERROR

        # Check if there are running actions
        for action_container in self.actions.values():
            if action_container.started and not action_container.finished:
                action_container.action.stop()
    # ------------------------------------------------------------------------------------------------------------------


# ======================================================================================================================
@dataclasses.dataclass
class ExperimentAgentContainer:
    id: str
    agent: AgentContainer
    algorithm: AlgorithmAgentContainer


# === EXPERIMENT HANDLER ===============================================================================================
@dataclasses.dataclass
class ExperimentSample:
    time: float  # Internal time of the experiment
    time_absolut: float  # Absolute time of the experiment
    id: str  # Experiment ID
    agents: AgentManager_Sample  # Sample containing all true agent data


@dataclasses.dataclass
class ExperimentSettings:
    update_time_algorithm: float = 0.2
    update_time_agents: float = 0.1


class AlgorithmState(enum.StrEnum):
    RUNNING = "running"
    IDLE = "idle"


class FRODO_Experiment_Handler:
    agents: dict[str, ExperimentAgentContainer]

    agent_manager: FRODO_AgentManager
    algorithm_manager: FRODO_AlgorithmManager
    algorithm_state: AlgorithmState = AlgorithmState.IDLE

    step: int = 0

    _exit: bool = False
    _thread: threading.Thread

    # === INIT =========================================================================================================
    def __init__(self,
                 settings: ExperimentSettings,
                 agent_manager: FRODO_AgentManager,
                 algorithm_manager: FRODO_AlgorithmManager, ):
        self.settings = settings
        self.agents = {}
        self.commands = self.Commands(self)
        self.logger = Logger('Experiment Handler', 'DEBUG')

        self.agent_manager = agent_manager
        self.algorithm_manager = algorithm_manager

        self.timer = IntervalTimer(interval=self.settings.update_time_agents, raise_race_condition_error=False)
        self._thread = threading.Thread(target=self._task, daemon=True)
        register_exit_callback(self.close)

    # === METHODS ======================================================================================================
    def init(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.logger.warning("Starting Experiment Handler in thread. This is for debug purposes only.")
        self._thread.start()

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        self._exit = True
        if self._thread is not None and self._thread.is_alive():
            self._thread.join()

    # ------------------------------------------------------------------------------------------------------------------
    def initialize(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def update(self):
        """
        Runs the update on the whole experiment (simulation, agent manager, algorithm manager ...)
        """

        self.logger.info(f"Step {self.step}")
        # Update the agent manager?
        self.agent_manager.update()

        if self.algorithm_state == AlgorithmState.RUNNING:
            # 1. Do the prediction
            self._prediction()

            # 2. Do the correction
            self._correction()

        self.step += 1

    # ------------------------------------------------------------------------------------------------------------------

    # === PRIVATE METHODS ==============================================================================================
    def _prediction(self):
        # we need to get the agent inputs and we need to put those in the algorithm manager
        prediction_data = {}

        for agent_id, container in self.agents.items():
            prediction_data[agent_id] = AlgorithmAgentUpdateData(
                input=AlgorithmAgentInput(
                    v=container.agent.input.v,
                    psi_dot=container.agent.input.psi_dot
                )
            )

        self.algorithm_manager.prediction(prediction_data)

    # ------------------------------------------------------------------------------------------------------------------
    def _correction(self):

        # Collect the measurements and update the algorithm manager
        correction_data = {}

        for agent_id, container in self.agents.items():
            agent_correction_data = []

            for measurement in container.agent.measurements:
                measurement_converted = AlgorithmAgentMeasurement(
                    agent_from=agent_id,
                    agent_to=measurement.agent_to,
                    measurement=measurement.measurement,
                    covariance=measurement.covariance
                )
                agent_correction_data.append(measurement_converted)

            correction_data[agent_id] = agent_correction_data

        self.algorithm_manager.correction(correction_data)

    # ------------------------------------------------------------------------------------------------------------------
    def _task(self):
        self.timer.reset()
        while not self._exit:
            self.update()
            self.timer.sleep_until_next()

    # === CLASSES ======================================================================================================
    class Commands(CommandSet):

        def __init__(self, handler: FRODO_Experiment_Handler):
            super().__init__('experiment')
            self.handler = handler
