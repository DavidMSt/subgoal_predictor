import dataclasses
import enum
import time
from copy import copy

import numpy as np
import qmt

from core.utils.events import event_definition, Event
from core.utils.logging_utils import Logger
from core.utils.orientation.orientation_3d import calculate_intersection, vector_from_local_to_global, \
    vector_from_global_to_local
from extensions.optitrack.optitrack import OptiTrack, RigidBodySample
from core.utils.callbacks import callback_definition, CallbackContainer
from robots.bilbo.robot.bilbo_definitions import BILBO_OptiTrack_Definition, BILBO_Config, BILBO_OriginConfig, \
    BILBO_LimboMarkerConfig


@dataclasses.dataclass
class TrackedOrigin_State:
    x: float
    y: float
    z: float
    orientation: np.ndarray


class TrackedOrigin:
    id: str
    definition: BILBO_OriginConfig
    state: TrackedOrigin_State
    tracking_valid: bool = False

    # === INIT =========================================================================================================
    def __init__(self, id: str, definition: BILBO_OriginConfig):
        self.id = id
        self.definition = definition
        self.state = TrackedOrigin_State(x=0, y=0, z=0, orientation=np.asarray([1, 0, 0, 0]))

    # === METHODS ======================================================================================================
    def update(self, data: RigidBodySample):
        # Check if tracking is valid
        if not data.valid:
            self.tracking_valid = False
            return

        origin = data.markers[self.definition.origin]
        x_axis_end = data.markers[self.definition.x_axis_end]
        y_axis_end = data.markers[self.definition.y_axis_end]

        x_axis = x_axis_end - origin
        y_axis = y_axis_end - origin

        orientation = qmt.quatFrom2Axes(
            x=x_axis,
            y=y_axis,
            exactAxis='x'
        )

        local_offset = np.asarray([
            self.definition.offset_x,
            self.definition.offset_y,
            self.definition.offset_z + 0.5 * self.definition.marker_size
        ])

        # Rotate offset into global frame
        global_offset = vector_from_local_to_global(
            vector_in_local_frame=local_offset,
            local_orientation=orientation
        )

        # Final origin position in global frame
        position = origin + global_offset

        self.state = TrackedOrigin_State(
            x=position[0],
            y=position[1],
            z=position[2],
            orientation=orientation
        )
        self.tracking_valid = True
        self.state = TrackedOrigin_State(x=position[0], y=position[1], z=position[2], orientation=orientation)


@dataclasses.dataclass
class TrackedLimboBar_State:
    x: float
    y: float
    psi: float = 0


@callback_definition
class TrackedLimboBar_Callbacks:
    update: CallbackContainer


@event_definition
class TrackedLimboBar_Events:
    update: Event


class TrackedLimboBar:
    id: str
    config: BILBO_LimboMarkerConfig
    origin: TrackedOrigin | None = None
    tracking_valid: bool = False
    state: TrackedLimboBar_State

    # ------------------------------------------------------------------------------------------------------------------
    def __init__(self, id: str, config: BILBO_LimboMarkerConfig, origin: TrackedOrigin | None = None):
        self.id = id
        self.config = config
        self.origin = origin
        self.state = TrackedLimboBar_State(x=0, y=0)

        self.callbacks = TrackedLimboBar_Callbacks()
        self.events = TrackedLimboBar_Events()

    # ------------------------------------------------------------------------------------------------------------------
    def update(self, data: RigidBodySample):
        if not data.valid:
            self.tracking_valid = False
            return

        self.tracking_valid = True

        x_axis_point_start = np.asarray(data.markers[self.config.x_start])
        x_axis_point_end = np.asarray(data.markers[self.config.x_end])
        y_axis_point_start = np.asarray(data.markers[self.config.y_start])
        y_axis_point_end = np.asarray(data.markers[self.config.y_end])

        position = calculate_intersection(x_axis_point_start,
                                          x_axis_point_end,
                                          y_axis_point_start,
                                          y_axis_point_end)

        # Calculate the x-axis direction vector (local x-axis of the limbo bar)
        x_axis_direction = x_axis_point_end - x_axis_point_start

        if self.origin is not None:
            diff_vector = position - np.asarray([self.origin.state.x, self.origin.state.y, self.origin.state.z])

            position = vector_from_global_to_local(
                vector_in_global_frame=diff_vector,
                target_frame_global_orientation=self.origin.state.orientation
            )

            # Transform the x-axis direction into the origin's frame
            x_axis_direction = vector_from_global_to_local(
                vector_in_global_frame=x_axis_direction,
                target_frame_global_orientation=self.origin.state.orientation
            )

        # Calculate psi: angle of the x-axis direction with respect to global x-axis, plus limbo_direction offset
        psi = np.arctan2(x_axis_direction[1], x_axis_direction[0]) + self.config.limbo_direction

        self.state = TrackedLimboBar_State(x=position[0], y=position[1], psi=psi)

        self.callbacks.update.call(self.state, self.tracking_valid)
        self.events.update.set(self.state)


# ======================================================================================================================


@dataclasses.dataclass
class TrackedBILBO_State:
    x: float
    y: float
    z: float
    theta: float
    psi: float


@callback_definition
class TrackedBILBO_Callbacks:
    sample: CallbackContainer


@event_definition
class TrackedBILBO_Events:
    update: Event


class TrackedBILBO:
    id: str
    config: BILBO_Config
    state: TrackedBILBO_State
    tracking_valid: bool = False

    origin: TrackedOrigin | None = None

    callbacks: TrackedBILBO_Callbacks

    # === INIT =========================================================================================================
    def __init__(self, id: str, config: BILBO_Config, origin: TrackedOrigin = None):
        self.id = id
        self.config = config
        self.state = TrackedBILBO_State(x=0, y=0, z=self.config.model.wheel_diameter / 2, theta=0, psi=0)
        self.origin = origin

        self.callbacks = TrackedBILBO_Callbacks()
        self.events = TrackedBILBO_Events()

    # ------------------------------------------------------------------------------------------------------------------
    def update(self, data: RigidBodySample):
        # Check if tracking is valid
        if not data.valid:
            self.tracking_valid = False
            return

        x_axis_point_start = np.asarray(data.markers[self.config.optitrack.point_x_axis_start])
        x_axis_point_end = np.asarray(data.markers[self.config.optitrack.point_x_axis_end])
        y_axis_point_start = np.asarray(data.markers[self.config.optitrack.point_y_axis_start])
        y_axis_point_end = np.asarray(data.markers[self.config.optitrack.point_y_axis_end])

        center_point = calculate_intersection(x_axis_point_start,
                                              x_axis_point_end,
                                              y_axis_point_start,
                                              y_axis_point_end)

        x_vector = x_axis_point_end - center_point
        y_vector = y_axis_point_end - center_point

        orientation = qmt.quatFrom2Axes(
            x=x_vector,
            y=y_vector,
            exactAxis='x'
        )

        wheel_mid_point_local = np.asarray([
            0,
            0,
            - (self.config.model.vertical_offset + 0.5 * self.config.optitrack.marker_size)
        ])

        wheel_mid_point_global = center_point + vector_from_local_to_global(
            vector_in_local_frame=wheel_mid_point_local,
            local_orientation=orientation
        )

        # Calculate the orientation relative to the origin
        if self.origin is not None:
            orientation = qmt.qmult(
                qmt.qinv(copy(self.origin.state.orientation)), orientation)

        psi, theta, _ = qmt.eulerAngles(orientation, axes='zyx', intrinsic=True)

        # Calculate the position relative to the origin
        if self.origin is not None:
            # 1. Get the global difference vector
            diff_vector = wheel_mid_point_global - np.asarray([
                self.origin.state.x,
                self.origin.state.y,
                self.origin.state.z
            ])

            # 2. Transform this difference vector into the local frame of the origin
            position = vector_from_global_to_local(
                vector_in_global_frame=diff_vector,
                target_frame_global_orientation=self.origin.state.orientation
            )
        else:
            position = wheel_mid_point_global

        self.state = TrackedBILBO_State(x=position[0], y=position[1], z=position[2], theta=theta, psi=psi)

        self.tracking_valid = True
        self.callbacks.sample.call(self.state, self.tracking_valid)
        self.events.update.set(self.state)


# =====================================================================================================================

@callback_definition
class BILBO_Tracker_Callbacks:
    new_sample: CallbackContainer
    description_received: CallbackContainer


@event_definition
class BILBO_Tracker_Events:
    new_sample: Event
    description_received: Event
    initialized: Event
    error: Event
    new_rigid_body: Event
    new_tracked_object: Event = Event(copy_data_on_set=False)
    tracked_object_removed: Event = Event(copy_data_on_set=False)


@callback_definition
class BILBO_Tracker_Callbacks:
    new_sample: CallbackContainer
    description_received: CallbackContainer
    new_rigid_body: CallbackContainer


class BILBO_Tracker_Status(enum.StrEnum):
    RUNNING = "RUNNING"
    DISABLED = "DISABLED"
    NONE = "NONE"


class BILBO_Tracker:
    optitrack: OptiTrack

    status: BILBO_Tracker_Status = BILBO_Tracker_Status.NONE
    rigid_bodies: dict[str, dict]

    robots: dict[str, TrackedBILBO]
    origin: TrackedOrigin | None = None
    limbo_bar: TrackedLimboBar | None = None
    events: BILBO_Tracker_Events

    samples: int = 0

    # === INIT =========================================================================================================
    def __init__(self, max_sample_rate: int = 30, server_address: str = 'palantir.lan'):
        self.logger = Logger('BILBO Tracker', 'DEBUG')

        self.rigid_bodies = {}
        self.sample = None

        self.robots = {}
        self.origin = None

        self.events = BILBO_Tracker_Events()
        self.callbacks = BILBO_Tracker_Callbacks()

        self.optitrack = OptiTrack(max_sample_rate=max_sample_rate, server_address=server_address)
        self.optitrack.events.sample.on(self._onSample)
        self.optitrack.callbacks.description_received.register(self._onDescriptionReceived)

    # === METHODS ======================================================================================================
    def init(self):
        self.optitrack.init()

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        success = self.optitrack.start()

        if not success:
            self.logger.warning("Could not start OptiTrack. Tracking disabled")
            self.status = BILBO_Tracker_Status.DISABLED
            self.events.error.set()
            return False
        self.logger.info("Starting Tracker")

        return True

    # ------------------------------------------------------------------------------------------------------------------
    def add_robot(self, robot_id: str, config: BILBO_Config) -> TrackedBILBO | None:
        if self.status == BILBO_Tracker_Status.DISABLED:
            return None

        if robot_id in self.robots:
            self.logger.error(f"BILBO robot {robot_id} already exists")
            return None

        if robot_id not in self.rigid_bodies:
            self.logger.error(f"BILBO robot {robot_id} not found in rigid bodies")
            return None

        robot = TrackedBILBO(id=robot_id,
                             config=config,
                             origin=self.origin)

        self.robots[robot_id] = robot
        self.logger.info(f"BILBO robot {robot_id} added to tracker")
        self.events.new_tracked_object.set(robot)
        return robot

    # ------------------------------------------------------------------------------------------------------------------
    def remove_robot(self, robot_id: str):

        if self.status == BILBO_Tracker_Status.DISABLED:
            return

        if robot_id in self.robots:
            del self.robots[robot_id]
            self.logger.info(f"BILBO robot {robot_id} removed from tracker")
        else:
            self.logger.error(f"BILBO robot {robot_id} does not exist")

        self.events.tracked_object_removed.set(robot_id)

    # ------------------------------------------------------------------------------------------------------------------
    def add_origin(self, origin_id: str, config: BILBO_OriginConfig) -> TrackedOrigin | None:

        if self.status == BILBO_Tracker_Status.DISABLED:
            return None

        if self.origin is not None:
            self.logger.error(f"Origin {origin_id} already exists")
            return None

        if origin_id not in self.rigid_bodies:
            self.logger.error(f"Origin {origin_id} not found in rigid bodies")
            return None

        self.origin = TrackedOrigin(id=origin_id, definition=config)
        self.logger.info(f"Origin {origin_id} added to tracker")

        for robot in self.robots.values():
            if robot.origin is None:
                robot.origin = self.origin

        if self.limbo_bar is not None:
            self.limbo_bar.origin = self.origin

        self.events.new_tracked_object.set(self.origin)
        return self.origin

    # ------------------------------------------------------------------------------------------------------------------
    def add_limbo_bar(self, limbo_bar_id: str, config: BILBO_LimboMarkerConfig) -> TrackedLimboBar | None:
        limbo_bar = TrackedLimboBar(id=limbo_bar_id, config=config, origin=self.origin)
        self.limbo_bar = limbo_bar
        self.events.new_tracked_object.set(self.limbo_bar)
        return self.limbo_bar

    # ------------------------------------------------------------------------------------------------------------------
    def get_object_by_id(self, id: str) -> TrackedBILBO | None:
        if id in self.robots:
            return self.robots[id]
        else:
            return None

    # === PRIVATE METHODS ==============================================================================================
    def _onSample(self, sample: dict[str, RigidBodySample]):
        self.sample = sample
        self.samples += 1

        for robot in self.robots.values():
            robot.tracking_valid = False

        if self.origin is not None:
            if self.origin.id in sample:
                self.origin.update(sample[self.origin.id])
                self.origin.tracking_valid = sample[self.origin.id].valid
            else:
                self.origin.tracking_valid = False

        if self.limbo_bar is not None:
            if self.limbo_bar.id in sample:
                self.limbo_bar.update(sample[self.limbo_bar.id])
                self.limbo_bar.tracking_valid = sample[self.limbo_bar.id].valid

            else:
                self.limbo_bar.tracking_valid = False

        for name, data in sample.items():
            if name not in self.rigid_bodies:
                self.logger.info(f"New rigid body found: {name}")
                self.callbacks.new_rigid_body.call(name)
                self.events.new_rigid_body.set(name)

            if name in self.robots:
                self.robots[name].update(data)
                self.robots[name].tracking_valid = data.valid

        self.callbacks.new_sample.call()
        self.events.new_sample.set()

    # ------------------------------------------------------------------------------------------------------------------
    def _onDescriptionReceived(self, rigid_bodies: dict):
        self.logger.info(f"Received description from OptiTrack: {rigid_bodies}")

        for id in rigid_bodies:
            self.rigid_bodies[id] = rigid_bodies[id]

        # for id in rigid_bodies:
        #     bilbo_definition = get_tracked_bilbo_definition_by_id(id)
        #     if bilbo_definition is not None:
        #         if id in self.robots:
        #             self.logger.warning(f"BILBO robot {id} already exists")
        #             return
        #         else:
        #             robot = TrackedBILBO(id=id, definition=bilbo_definition, origin=self.origin)
        #             self.robots[id] = robot
        #             self.logger.info(f"BILBO robot {id} added to tracker")

        self.status = BILBO_Tracker_Status.RUNNING
        self.callbacks.description_received.call(rigid_bodies)
        self.events.description_received.set()
        self.events.initialized.set()


if __name__ == '__main__':
    tracker = BILBO_Tracker()
    tracker.init()
    tracker.start()

    while True:
        time.sleep(1)
