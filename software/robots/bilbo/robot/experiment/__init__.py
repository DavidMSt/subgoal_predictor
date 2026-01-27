"""
BILBO Experiment Module

This module provides experiment handling for BILBO robots on the host side.

Key classes:
- ExperimentDefinition: Define experiments (from YAML, JSON, or programmatically)
- ExperimentActionDefinition: Define individual actions within experiments
- ExperimentBuilder: Fluent API for building experiments programmatically
- BILBO_ExperimentHandler: Run experiments and handle lifecycle events

Action helper functions (for programmatic experiment creation):
- beep(), speak(), wait_time(), wait_ticks()
- set_mode(), set_velocity(), set_input()
- run_trajectory(), set_marker(), enable_external_input()
- reset(), parallel(), set_tic()
- wait_event(), wait_until_tick()

Example usage:
    # From YAML file
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
"""

# Core definitions
from robots.bilbo.robot.experiment.experiment_definitions import (
    # Trajectories
    BILBO_InputTrajectory,
    BILBO_InputTrajectoryStep,
    BILBO_StateTrajectory,
    BILBO_TrajectoryData,
    BILBO_OutputTrajectory,

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

    # File I/O
    BILBO_InputFileData,
    INPUT_TRAJECTORY_FILE_EXTENSION,
    write_input_file,
    read_input_file,
)

# Experiment handler
from robots.bilbo.robot.experiment.bilbo_experiment import (
    BILBO_ExperimentHandler,
    BILBO_ExperimentHandler_Events,
    BILBO_ExperimentHandler_Status,
)

__all__ = [
    # Trajectories
    "BILBO_InputTrajectory",
    "BILBO_InputTrajectoryStep",
    "BILBO_StateTrajectory",
    "BILBO_TrajectoryData",
    "BILBO_OutputTrajectory",

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

    # File I/O
    "BILBO_InputFileData",
    "INPUT_TRAJECTORY_FILE_EXTENSION",
    "write_input_file",
    "read_input_file",

    # Handler
    "BILBO_ExperimentHandler",
    "BILBO_ExperimentHandler_Events",
    "BILBO_ExperimentHandler_Status",
]
