/*
 * firmware_setting.h
 *
 *  Created on: 3 Mar 2023
 *      Author: lehmann_workstation
 */

#ifndef FIRMWARE_SETTINGS_H_
#define FIRMWARE_SETTINGS_H_

/* USER SETTINGS */
//#define BILBO_DRIVE_SIMPLEXMOTION_RS485
#define BILBO_DRIVE_SIMPLEXMOTION_CAN

#define BILBO_MODEL_NORMAL // Define one of these: BILBO_MODEL_NORMAL, BILBO_MODEL_SMALL, BILBO_MODEL_BIG
//#define BILBO_MODEL_BIG
//#define BILBO_MODEL_SMALL

// Hardware safety line: STM32 GPIO connected to motor IN1.
// Directly triggers motor quickstop independent of CAN communication.
// Requires wiring STM32 GPIO to IN1 on both SimplexMotion motors.
#define ENABLE_MOTOR_SHUTDOWN_LINE 0

// REVISION
#define TWIPR_FIRMWARE_REVISION_MAJOR 0x02
#define TWIPR_FIRMWARE_REVISION_MINOR 0x02

// FIRMWARE MODES
#define TWIPR_FIRMWARE_USE_MOTORS 1

// Main Task Frequency
#define BILBO_CONTROL_TASK_TIME 0.01 // seconds
#define TWIPR_CONTROL_TASK_FREQ 100

// Control
#define TWIPR_SAFETY_MAX_WHEEL_SPEED 75

// Motor speed measurement filter (0 = no filtering, 4 = default, 15 = max)
// Higher values smooth low-speed noise but add measurement lag
#define SIMPLEXMOTION_SPEED_FILTER 7

// Motor encoder resolution in bits (12 = 4096, 13 = 8192, 14 = 16384 counts/rev)
// Higher resolution improves low-speed measurement but adds position noise
#define SIMPLEXMOTION_ENCODER_RESOLUTION 12

// Control - Trajectories
#define TWIPR_SEQUENCE_TIME 30 // seconds

// Logging
#define TWIPR_FIRMWARE_SAMPLE_BUFFER_TIME 0.1 // seconds

#endif /* FIRMWARE_SETTINGS_H_ */
