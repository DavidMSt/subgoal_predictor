/*
 * bilbo_position_control.h
 *
 *  Created on: Jan 9, 2026
 *      Author: lehmann
 */

#ifndef CONTROL_BILBO_POSITION_CONTROL_H_
#define CONTROL_BILBO_POSITION_CONTROL_H_

#include <cstdint>
#include "twipr_estimation.h"

/**
 * @brief Configuration parameters for the BILBO position controller.
 *
 * Notes:
 * - kp_* and ki_* are applied in PI controllers for distance and angle.
 * - Ts is the controller update period in seconds.
 * - lookahead_distance is used for carrot-chasing (softens heading when far).
 * - allow_reverse/backwards_switch_angle let the robot drive backwards to the target
 *   (diff-drive), instead of turning all the way around first.
 * - arrival tolerances + arrival_time define completion:
 *   The robot must be inside the tolerance region continuously for arrival_time.
 * - max_speed_forward/max_speed_turn are default saturation limits. Per-command
 *   overrides can be provided, but if override <= 0, the configured defaults apply.
 */
struct bilbo_position_control_config_t {
	float kp_linear;
	float ki_linear;

	float kp_angular;
	float ki_angular;

	float Ts;
	float lookahead_distance;

	uint8_t allow_reverse;        // prefer uint8_t over bool for wire stability
	float backwards_switch_angle; // [rad]

	float distance_arrival_tolerance; // [m]
	float angle_arrival_tolerance;    // [rad]
	float arrival_time;               // [s]

	float max_speed_forward; // [m/s]
	float max_speed_turn;    // [rad/s]
};

/**
 * @brief Position reference for POSITION_TO_POINT mode.
 */
struct position_reference_t {
	float x_target;
	float y_target;
};

/**
 * @brief Heading reference for TURN_TO_HEADING mode.
 */
struct heading_reference_t {
	float psi_target;
};

enum class bilbo_position_control_mode_t : uint8_t {
	NONE = 0,
	POSITION_TO_POINT = 1,
	TURN_TO_HEADING = 2,
};

/**
 * @brief Command for driving to a point.
 * - max_speed: if <= 0, controller uses config.max_speed_forward
 * - timeout:   if > 0, command will be aborted after timeout seconds
 */
struct position_command_t {
	uint16_t id;
	position_reference_t position_ref;
	float max_speed;
	float timeout;
};

/**
 * @brief Command for turning to an absolute heading.
 * - max_angular_speed: if <= 0, controller uses config.max_speed_turn
 * - timeout:          if > 0, command will be aborted after timeout seconds
 */
struct heading_command_t {
	uint16_t id;
	heading_reference_t heading_ref;
	float max_angular_speed;
	float timeout;
};

/**
 * @brief Controller output in unicycle form (diff-drive compatible).
 * v_cmd       : forward velocity command [m/s]
 * psi_dot_cmd : yaw rate command [rad/s]
 */
struct bilbo_position_control_output_t {
	float v_cmd;
	float psi_dot_cmd;
};

/**
 * @brief Debug/telemetry bundle.
 */
struct bilbo_position_control_data_t {
	bilbo_position_control_mode_t current_mode;
	position_command_t current_position_command;
	heading_command_t current_heading_command;
	bilbo_position_control_output_t current_output;
	bool is_executing_command;
};

/* ---------------------------------------------------------------------------------------- */
struct bilbo_position_control_callbacks_t {
	core_utils_CallbackContainer<4, uint16_t> element_finished;
	core_utils_CallbackContainer<4, uint16_t> element_timeout;
};

class BILBO_PositionControl {
public:
	BILBO_PositionControl();

	/**
	 * @brief Main update function (call every Ts).
	 *
	 * Behavior:
	 * - If no command is active, outputs are zero.
	 * - POSITION_TO_POINT: carrot-chasing PI with optional reverse.
	 * - TURN_TO_HEADING: PI on heading error.
	 * - Completion requires holding tolerances for arrival_time.
	 * - Timeout: if current command timeout > 0, aborts after elapsed >= timeout.
	 */
	bilbo_position_control_output_t update(bilbo_position_state_t current_state);

	void set_config(bilbo_position_control_config_t config);
	void reset();
	bilbo_position_control_config_t get_config();

	bool set_position_command(position_command_t command);
	bool set_heading_command(heading_command_t command);
	void abort_current_command();

	bool is_executing_command();

	bool is_finished() {
		return !is_executing_command();
	}

	bilbo_position_control_data_t get_data();

	bilbo_position_control_mode_t get_current_mode() {
		return this->current_mode;
	}

	bilbo_position_control_config_t config;
	bilbo_position_control_mode_t current_mode;

	bilbo_position_control_callbacks_t callbacks;

private:
	// Called when a command is completed normally (arrival-hold satisfied).
	void _on_command_finished();

	// Called when a command exceeds its timeout (timeout > 0).
	void _on_timeout();

	// Controllers for each mode
	bilbo_position_control_output_t _position_control_to_point(
			bilbo_position_state_t current_state,
			float x_target,
			float y_target,
			float max_speed_forward_override);

	bilbo_position_control_output_t _turn_to_heading(
			bilbo_position_state_t current_state,
			float psi_target,
			float max_turn_speed_override);

	// Active commands
	position_command_t _current_position_command;
	heading_command_t _current_heading_command;

	// Telemetry
	bilbo_position_control_data_t _data;

	// Internal PI controller state (integrator contributions)
	float _position_integral_error; // contributes directly to v_pi [m/s]
	float _angle_integral_error;    // contributes directly to w_pi [rad/s]

	// Completion / arrival-hold logic
	float _arrival_hold_time;       // how long we've been continuously "inside"
	bool _was_inside_arrival_region;

	// Current element bookkeeping
	uint16_t _current_element_id;

	// Timeout bookkeeping
	uint32_t _element_start_tick;
};

#endif /* CONTROL_BILBO_POSITION_CONTROL_H_ */
