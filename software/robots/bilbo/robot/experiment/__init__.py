"""
BILBO Experiment Module

This module provides experiment handling for BILBO robots on the host side.

Key classes:
- ExperimentDefinition: Define experiments (from YAML, JSON, or programmatically)
- ExperimentActionDefinition: Define individual actions within experiments
- ExperimentBuilder: Fluent API for building experiments programmatically
- BILBO_ExperimentHandler: Run experiments and handle lifecycle events

Action Registry (for parsing and validation):
- ActionParameter, ActionEntry: Declarative action definitions
- ActionRegistry: Registry of all available action types
- ExperimentParser: Parse and validate experiment files/dicts
- get_registry(): Access the global action registry
- validate_experiment(): Validate without raising exceptions

Action helper functions (for programmatic experiment creation):
- beep(), speak(), wait_time(), wait_ticks()
- set_mode(), set_velocity(), set_input()
- run_trajectory(), set_marker(), enable_external_input()
- reset(), parallel(), set_tic()
- wait_event(), wait_until_tick()

Example usage:
    # From YAML file with validation
    from robots.bilbo.robot.experiment import parse_experiment_file
    exp_dict = parse_experiment_file("my_experiment.yaml")

    # Using ExperimentDefinition
    exp = ExperimentDefinition.from_file("my_experiment.yaml")
    data = experiment_handler.run_experiment(exp, blocking=True)

    # Programmatically with builder
    exp = (ExperimentBuilder("test", "Test experiment")
           .speak("Starting test")
           .wait(time_s=1.0)
           .set_mode("BALANCING")
           .wait(time_s=10.0)
           .set_mode("OFF")
           .build())
    data = experiment_handler.run_experiment(exp, blocking=True)

    # Using helper functions
    exp = ExperimentDefinition(
        id="test",
        description="Test experiment",
        actions=[
            speak("Starting", id="speak_0"),
            wait_time(time_s=1.0, id="wait_0"),
            set_mode("BALANCING", id="mode_0"),
        ]
    )

    # Introspect available actions
    from robots.bilbo.robot.experiment import get_registry, get_available_actions
    for action_info in get_available_actions():
        print(f"{action_info['type']}: {action_info['description']}")
"""

# Action registry and parser (experiment_actions.py)
from robots.bilbo.robot.experiment.experiment_actions import (
    # Parameter and action definitions
    ActionParameter,
    ActionEntry,
    ActionRegistry,
    ExperimentParser,

    # Registry access
    get_registry,
    register_action,

    # Convenience functions
    parse_experiment_file,
    parse_experiment_dict,
    validate_experiment,
    get_available_actions,
    get_action_info,

    # Converters (for custom actions)
    parse_time_ms,
    parse_control_mode,
    normalize_path_points,
    normalize_waypoints,
)

# Core definitions
from robots.bilbo.robot.experiment.experiment_definitions import (
    # Trajectories
    InputTrajectory,
    InputTrajectoryStep,
    StateTrajectory,
    TrajectoryData,
    OutputTrajectory,

    # Action parameter dataclasses (for type checking)
    BeepActionParams,
    SetModeActionParams,
    SetTICActionParams,
    SpeakActionParams,
    SetMarkerActionParams,
    EnableExternalInputActionParams,
    SetVelocityActionParams,
    SetInputActionParams,
    WaitTimeActionParams,
    WaitTicksActionParams,
    WaitUntilTickActionParams,
    WaitEventActionParams,
    RunTrajectoryActionParams,
    ResetActionParams,
    ParallelActionParams,
    ACTION_PARAMS_MAPPING,
    ALLOWED_ACTIONS,
    ActionType,

    # Experiment definitions
    ExperimentActionDefinition,
    ExperimentDefinition,
    ExperimentActionData,
    ExperimentMetaData,
    ExperimentData,

    # Builder
    ExperimentBuilder,

    # Action helper functions
    beep,
    set_mode,
    speak,
    wait_time,
    wait_ticks,
    set_velocity,
    set_input,
    run_trajectory,
    set_marker,
    enable_external_input,
    reset,
    parallel,
    set_tic,
    wait_event,
    wait_until_tick,
    func,
    set_feedback_gain,
    reset_control,

    # Position control helper functions
    move_to,
    turn_to,
    stop_path,
    follow_path,
    wait_position_event,

    # Position control action params
    MoveToActionParams,
    TurnToActionParams,
    StopPathActionParams,
    FollowPathActionParams,
    FollowPathWaypointDef,
    WaitPositionEventActionParams,
    FuncActionParams,
    SetFeedbackGainActionParams,
    ResetControlActionParams,

    # File I/O
    InputTrajectoryFileData,
    OutputTrajectoryFileData,
    INPUT_TRAJECTORY_FILE_EXTENSION,
    OUTPUT_TRAJECTORY_FILE_EXTENSION,
    write_input_file,
    read_input_file,
    write_output_file,
    read_output_file,
)

# Experiment handler
from robots.bilbo.robot.experiment.bilbo_experiment import (
    BILBO_ExperimentHandler,
    BILBO_ExperimentHandler_Events,
    BILBO_ExperimentHandler_Status,
)

# Multi-trial experiments (host-side proxies)
from robots.bilbo.robot.experiment.dilc import (
    DILC_Experiment,
    DILC_Experiment_Settings,
    DILC_Experiment_State,
    DILC_Experiment_Events,
    DILC_Trial_Result,
    DILC_Trajectory_Data,
    DILC_Trial_Data,
    DILC_Results,
    DILC_Results_Meta,
    DILC_InitialConditions,
    DILC_Experiment_Meta_Settings,
    FIR_Design_Params,
    load_dilc_settings_from_yaml,
)

__all__ = [
    # Action registry and parser
    "ActionParameter",
    "ActionEntry",
    "ShorthandRule",
    "ActionRegistry",
    "ExperimentParser",
    "get_registry",
    "register_action",
    "parse_experiment_file",
    "parse_experiment_dict",
    "validate_experiment",
    "get_available_actions",
    "get_action_info",
    "parse_time_ms",
    "parse_control_mode",
    "normalize_path_points",
    "normalize_waypoints",

    # Trajectories
    "InputTrajectory",
    "InputTrajectoryStep",
    "StateTrajectory",
    "TrajectoryData",
    "OutputTrajectory",

    # Action parameter dataclasses
    "BeepActionParams",
    "SetModeActionParams",
    "SetTICActionParams",
    "SpeakActionParams",
    "SetMarkerActionParams",
    "EnableExternalInputActionParams",
    "SetVelocityActionParams",
    "SetInputActionParams",
    "WaitTimeActionParams",
    "WaitTicksActionParams",
    "WaitUntilTickActionParams",
    "WaitEventActionParams",
    "RunTrajectoryActionParams",
    "ResetActionParams",
    "ParallelActionParams",
    "ACTION_PARAMS_MAPPING",
    "ALLOWED_ACTIONS",
    "ActionType",

    # Experiment definitions
    "ExperimentActionDefinition",
    "ExperimentDefinition",
    "ExperimentActionData",
    "ExperimentMetaData",
    "ExperimentData",

    # Builder
    "ExperimentBuilder",

    # Action helper functions
    "beep",
    "set_mode",
    "speak",
    "wait_time",
    "wait_ticks",
    "set_velocity",
    "set_input",
    "run_trajectory",
    "set_marker",
    "enable_external_input",
    "reset",
    "parallel",
    "set_tic",
    "wait_event",
    "wait_until_tick",
    "func",
    "set_feedback_gain",
    "reset_control",

    # Position control helper functions
    "move_to",
    "turn_to",
    "set_path",
    "set_waypoints",
    "start_path",
    "load_path",
    "stop_path",
    "wait_position_event",

    # Position control action params
    "MoveToActionParams",
    "TurnToActionParams",
    "SetPathActionParams",
    "SetWaypointsActionParams",
    "StartPathActionParams",
    "LoadPathActionParams",
    "StopPathActionParams",
    "WaitPositionEventActionParams",
    "FuncActionParams",
    "SetFeedbackGainActionParams",
    "ResetControlActionParams",
    "PathPointDef",
    "WaypointDef",

    # File I/O
    "InputTrajectoryFileData",
    "OutputTrajectoryFileData",
    "INPUT_TRAJECTORY_FILE_EXTENSION",
    "OUTPUT_TRAJECTORY_FILE_EXTENSION",
    "write_input_file",
    "read_input_file",
    "write_output_file",
    "read_output_file",

    # Handler
    "BILBO_ExperimentHandler",
    "BILBO_ExperimentHandler_Events",
    "BILBO_ExperimentHandler_Status",

    # Multi-trial experiments
    "DILC_Experiment",
    "DILC_Experiment_Settings",
    "DILC_Experiment_State",
    "DILC_Experiment_Events",
    "DILC_Trial_Result",
    "DILC_Trajectory_Data",
    "DILC_Trial_Data",
    "DILC_Results",
    "DILC_Results_Meta",
    "DILC_InitialConditions",
    "DILC_Experiment_Meta_Settings",
    "FIR_Design_Params",
    "load_dilc_settings_from_yaml",
]
