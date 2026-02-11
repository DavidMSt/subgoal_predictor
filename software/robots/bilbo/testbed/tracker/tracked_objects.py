import dataclasses
from copy import copy

import numpy as np
import qmt

from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.events import event_definition, Event
from core.utils.orientation.orientation_3d import vector_from_local_to_global, vector_from_global_to_local, \
    calculate_intersection
from extensions.optitrack import RigidBodySample
from robots.bilbo.robot.bilbo_definitions import BILBO_Config


# === OPTITRACK CONFIG DEFINITIONS =====================================================================================
@dataclasses.dataclass
class Origin_OptiTrack_Config:
    id: str
    points: list
    origin: int
    x_axis_end: int
    y_axis_end: int
    marker_size: float
    offset_x: float = 0.0
    offset_y: float = 0.0
    offset_z: float = 0.0


@dataclasses.dataclass(kw_only=True)
class LimboMarker_OptiTrack_Config:
    id: str = 'limbo-marker'
    points: list
    x_start: int
    x_end: int
    y_start: int
    y_end: int
    limbo_direction: float = -np.pi / 2


@dataclasses.dataclass(kw_only=True)
class BoxObstacle_OptiTrack_Config:
    id: str
    points: list
    origin: int
    x_axis_end: int
    y_axis_end: int


@dataclasses.dataclass(kw_only=True)
class WallObstacle_OptiTrack_Config:
    id: str
    points: list
    origin: int
    x_axis_end: int
    y_axis_end: int


# === ORIGIN ===========================================================================================================
@dataclasses.dataclass
class TrackedOrigin_State:
    x: float
    y: float
    z: float
    orientation: np.ndarray


class TrackedOrigin:
    id: str
    definition: Origin_OptiTrack_Config
    state: TrackedOrigin_State
    tracking_valid: bool = False

    # === INIT =========================================================================================================
    def __init__(self, id: str, definition: Origin_OptiTrack_Config):
        self.id = id
        self.definition = definition
        self.state = TrackedOrigin_State(x=0, y=0, z=0, orientation=np.asarray([1, 0, 0, 0]))

    # === METHODS ======================================================================================================
    def update(self, data: RigidBodySample):
        # Check if tracking is valid
        if not data.valid:
            self.tracking_valid = False
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


# === LIMBO BAR ========================================================================================================
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
    config: LimboMarker_OptiTrack_Config
    origin: TrackedOrigin | None = None
    tracking_valid: bool = False
    state: TrackedLimboBar_State

    # ------------------------------------------------------------------------------------------------------------------
    def __init__(self, id: str, config: LimboMarker_OptiTrack_Config, origin: TrackedOrigin | None = None):
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


# === BILBO ============================================================================================================
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


# === CUBE OBSTACLE ====================================================================================================
@dataclasses.dataclass
class TrackedCube_State:
    x: float
    y: float
    psi: float


@callback_definition
class TrackedCube_Callbacks:
    update: CallbackContainer


@event_definition
class TrackedCube_Events:
    update: Event


class TrackedBox:
    id: str
    state: TrackedCube_State
    tracking_valid: bool = False
    config: BoxObstacle_OptiTrack_Config
    origin: TrackedOrigin | None = None

    def __init__(self, id: str, config: BoxObstacle_OptiTrack_Config, origin: TrackedOrigin | None = None):
        self.id = id
        self.config = config
        self.origin = origin
        self.state = TrackedCube_State(x=0, y=0, psi=0)

        self.callbacks = TrackedCube_Callbacks()
        self.events = TrackedCube_Events()

    def update(self, data: RigidBodySample):
        if not data.valid:
            self.tracking_valid = False
            return

        self.tracking_valid = True

        origin_point = np.asarray(data.markers[self.config.origin])
        x_axis_end = np.asarray(data.markers[self.config.x_axis_end])
        y_axis_end = np.asarray(data.markers[self.config.y_axis_end])

        x_axis = x_axis_end - origin_point
        position = origin_point

        if self.origin is not None:
            diff_vector = position - np.asarray([self.origin.state.x, self.origin.state.y, self.origin.state.z])

            position = vector_from_global_to_local(
                vector_in_global_frame=diff_vector,
                target_frame_global_orientation=self.origin.state.orientation
            )

            x_axis = vector_from_global_to_local(
                vector_in_global_frame=x_axis,
                target_frame_global_orientation=self.origin.state.orientation
            )

        psi = np.arctan2(x_axis[1], x_axis[0])

        self.state = TrackedCube_State(x=position[0], y=position[1], psi=psi)

        self.callbacks.update.call(self.state, self.tracking_valid)
        self.events.update.set(self.state)


# === WALL OBSTACLE ====================================================================================================
@dataclasses.dataclass
class TrackedWall_State:
    x: float
    y: float
    psi: float


@callback_definition
class TrackedWall_Callbacks:
    update: CallbackContainer


@event_definition
class TrackedWall_Events:
    update: Event


class TrackedWall:
    id: str
    state: TrackedWall_State
    tracking_valid: bool = False
    config: WallObstacle_OptiTrack_Config
    origin: TrackedOrigin | None = None

    def __init__(self, id: str, config: WallObstacle_OptiTrack_Config, origin: TrackedOrigin | None = None):
        self.id = id
        self.config = config
        self.origin = origin
        self.state = TrackedWall_State(x=0, y=0, psi=0)

        self.callbacks = TrackedWall_Callbacks()
        self.events = TrackedWall_Events()

    def update(self, data: RigidBodySample):
        if not data.valid:
            self.tracking_valid = False
            return

        self.tracking_valid = True

        origin_point = np.asarray(data.markers[self.config.origin])
        x_axis_end = np.asarray(data.markers[self.config.x_axis_end])
        y_axis_end = np.asarray(data.markers[self.config.y_axis_end])

        x_axis = x_axis_end - origin_point
        position = origin_point

        if self.origin is not None:
            diff_vector = position - np.asarray([self.origin.state.x, self.origin.state.y, self.origin.state.z])

            position = vector_from_global_to_local(
                vector_in_global_frame=diff_vector,
                target_frame_global_orientation=self.origin.state.orientation
            )

            x_axis = vector_from_global_to_local(
                vector_in_global_frame=x_axis,
                target_frame_global_orientation=self.origin.state.orientation
            )

        psi = np.arctan2(x_axis[1], x_axis[0])

        self.state = TrackedWall_State(x=position[0], y=position[1], psi=psi)

        self.callbacks.update.call(self.state, self.tracking_valid)
        self.events.update.set(self.state)
