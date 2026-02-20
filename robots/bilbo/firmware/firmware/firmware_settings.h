/*
 * firmware_settings.h
 *
 * Central configuration for BILBO firmware.
 * Edit this file to build for different robot variants.
 *
 * Created on: 3 Mar 2023
 * Author: Dustin Lehmann
 */

#ifndef FIRMWARE_SETTINGS_H_
#define FIRMWARE_SETTINGS_H_

/* ================================================================
 * ROBOT VARIANT — uncomment ONE option per group
 * ================================================================ */

// Board hardware revision
//#define BOARD_REV_3
#define BOARD_REV_4

// Robot model (sets wheel diameter and wheel distance in bilbo_model.h)
#define BILBO_MODEL_NORMAL
//#define BILBO_MODEL_SMALL
//#define BILBO_MODEL_BIG

/* ================================================================
 * MOTOR INTERFACE — uncomment ONE
 * ================================================================ */

// SimplexMotion communication bus
//#define BILBO_DRIVE_SIMPLEXMOTION_RS485
#define BILBO_DRIVE_SIMPLEXMOTION_CAN

// Motor torque limit (Nm). Clamps all motor commands to this value.
#define BILBO_MOTOR_TORQUE_LIMIT 0.5

// Motor speed measurement filter (0 = none, 4 = default, 15 = max).
// Higher values smooth low-speed noise but add measurement lag.
#define SIMPLEXMOTION_SPEED_FILTER 5

// Motor encoder resolution in bits (12 = 4096, 13 = 8192, 14 = 16384 counts/rev).
// Higher resolution improves low-speed measurement but adds position noise.
#define SIMPLEXMOTION_ENCODER_RESOLUTION 13

// Hardware safety line: STM32 GPIO drives motor IN1 HIGH during operation,
// pulls LOW on error to trigger motor quickstop independent of CAN/RS485.
// Requires physical wiring from STM32 GPIO to IN1 on both motors.
#define ENABLE_MOTOR_SHUTDOWN_LINE 0

/* ================================================================
 * CONTROL LOOP
 * ================================================================ */

// Main control loop frequency (Hz). Estimation runs at the same rate.
#define BILBO_CONTROL_TASK_FREQ 100

// Max wheel speed before safety shutdown (rad/s)
#define BILBO_SAFETY_MAX_WHEEL_SPEED 75

// Enable/disable motor output (0 = dry-run, useful for testing without motors)
#define BILBO_FIRMWARE_USE_MOTORS 1

/* ================================================================
 * TRAJECTORIES & LOGGING
 * ================================================================ */

// Maximum trajectory duration (seconds). Determines pre-allocated buffer size.
#define BILBO_SEQUENCE_TIME 30

// Sample buffer aggregation time (seconds). Samples are collected for this
// duration before being sent to the host.
#define BILBO_FIRMWARE_SAMPLE_BUFFER_TIME 0.1

/* ================================================================
 * FIRMWARE REVISION — update when flashing new versions
 * ================================================================ */

#define BILBO_FIRMWARE_REVISION_MAJOR 0x03
#define BILBO_FIRMWARE_REVISION_MINOR 0x00

#endif /* FIRMWARE_SETTINGS_H_ */
