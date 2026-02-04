/*
 * bilbo_position_control.h
 *
 *  Created on: Jan 24, 2026
 *      Author: lehmann
 *
 *  Position control module for BILBO robot.
 *
 *  OVERVIEW
 *  ========
 *  This module provides three position control modes:
 *  1. TURN_TO_HEADING: Rotate in place to a target heading
 *  2. DRIVE_TO_POINT:  Drive to a single XY position
 *  3. FOLLOW_PATH:     Follow a sequence of waypoints using carrot-chase
 *
 *  PATH FOLLOWING ALGORITHM (FOLLOW_PATH mode)
 *  ===========================================
 *  Simple carrot-chase (pure pursuit) approach:
 *
 *  1. CARROT determines both DIRECTION and SPEED
 *     - Carrot moves along path segments (lines between waypoints)
 *     - Robot steers toward carrot point
 *     - Speed scales with carrot distance (closer = slower)
 *
 *  2. WAYPOINT WEIGHTS control corner behavior
 *     - weight=1.0: Carrot stops at waypoint until robot arrives (sharp corner)
 *     - weight=0.0: Carrot can advance freely to next segment (smooth)
 *     - Corner angle modulates weight effect: straight paths don't slow down
 *
 *  3. REVERSE MODE always enabled
 *     - Robot drives backwards when target is behind it
 *     - Hysteresis prevents oscillation at switching boundary
 *
 *  WAYPOINT TYPES
 *  ==============
 *  - PASS: Smooth transition, corner cutting based on weight
 *  - STOP: Robot must stop at this waypoint (last waypoint is always STOP)
 *
 *  COORDINATE SYSTEM
 *  =================
 *  - X: Forward direction (positive = forward)
 *  - Y: Left direction (positive = left)
 *  - psi: Heading angle (rad), 0 = positive X, positive = counter-clockwise
 */

#ifndef CONTROL_BILBO_POSITION_CONTROL_H_
#define CONTROL_BILBO_POSITION_CONTROL_H_

#include <cstdint>
#include <cmath>
#include "twipr_estimation.h"
#include "bilbo_message.h"
#include "firmware_addresses.h"

// Maximum number of waypoints that can be stored in the path buffer
#define BILBO_POSITION_CONTROL_MAX_WAYPOINTS 64

// ============================================================================
// ENUMERATIONS
// ============================================================================

/**
 * @brief Position control operating modes
 */
enum class bilbo_position_control_mode_t : uint8_t {
	IDLE = 0,  // No active command, outputs zero
	TURN_TO_HEADING = 1,  // Rotating in place to target heading
	DRIVE_TO_POINT = 2,  // Driving to a single point
	FOLLOW_PATH = 3   // Following waypoint path
};

/**
 * @brief Waypoint arrival behavior
 *
 * PASS: Robot smoothly transitions through this waypoint. The waypoint's
 *       weight parameter controls how tightly the robot follows the corner
 *       (weight=1 = sharp, weight=0 = smooth cut).
 *
 * STOP: Robot must come to a complete stop at this waypoint and optionally
 *       dwell for a specified time before proceeding. The last waypoint in
 *       a path is always treated as STOP regardless of this setting.
 */
enum class bilbo_waypoint_type_t : uint8_t {
	PASS = 0,  // Smooth transition, corner cutting allowed based on weight
	STOP = 1   // Must stop at this waypoint
};

/**
 * @brief Path execution state machine
 */
enum class bilbo_path_state_t : uint8_t {
	IDLE = 0,  // No path loaded or path completed
	RUNNING = 1,  // Actively following path
	PAUSED = 2   // Execution paused, internal state preserved
};

/**
 * @brief Position control events (sent to higher-level software)
 */
enum class position_control_event_t : uint8_t {
	PATH_STARTED = 0,   // Path execution started
	WAYPOINT_PASSED = 1,   // Robot passed through a waypoint (carrot advanced)
	WAYPOINT_REACHED = 2, // Robot entered waypoint's arrival tolerance (for STOP points)
	WAYPOINT_COMPLETED = 3,   // Waypoint fully completed (dwell finished)
	PATH_PAUSED = 4,   // Path execution paused
	PATH_RESUMED = 5,   // Path execution resumed
	PATH_FINISHED = 6,   // Path completed successfully
	PATH_TIMEOUT = 7,   // Path execution timed out
	PATH_ABORTED = 8,   // Path manually aborted
	MOVE_TO_POINT_STARTED = 9,   // Drive-to-point started
	MOVE_TO_POINT_COMPLETED = 10,  // Drive-to-point completed
	MOVE_TO_POINT_TIMEOUT = 11,  // Drive-to-point timed out
	TURN_TO_HEADING_STARTED = 12,  // Turn-to-heading started
	TURN_TO_HEADING_COMPLETED = 13, // Turn-to-heading completed
	TURN_TO_HEADING_TIMEOUT = 14,   // Turn-to-heading timed out
	MODE_CHANGED = 15,   // Position control mode changed
	WAYPOINT_BUFFER_FULL = 16   // Waypoint buffer is full, add_waypoint failed
};

// ============================================================================
// DATA STRUCTURES
// ============================================================================

/**
 * @brief Single waypoint definition
 *
 * @param x      World X coordinate [m]
 * @param y      World Y coordinate [m]
 * @param type   PASS or STOP behavior
 * @param weight Corner sharpness factor [0-1]:
 *               - 1.0: Robot must pass close to this point (sharp corner)
 *               - 0.5: Moderate corner cutting allowed
 *               - 0.0: Maximum corner cutting (smooth wide arc)
 *               Only affects PASS waypoints; STOP waypoints always use weight=1.0
 * @param speed  Maximum speed for approaching this waypoint [m/s]:
 *               - 0.0: Use path's max_speed setting (default)
 *               - >0:  Override with this specific speed limit
 *               Speed transitions smoothly between waypoints.
 *               Corner angle slowdown still applies (takes minimum).
 */
struct bilbo_waypoint_t {
	float x;                        // [m] world X coordinate
	float y;                        // [m] world Y coordinate
	bilbo_waypoint_type_t type;     // waypoint semantics
	float weight;                   // [0-1] corner sharpness (1=sharp, 0=smooth)
	float speed;                    // [m/s] max speed to this waypoint (0 = use path default)
};

/**
 * @brief Command to start path execution
 *
 * @param allow_reverse  If non-zero, robot may drive backwards when more efficient
 * @param timeout        Maximum time for path execution [s], 0 = no timeout
 * @param max_speed      Speed override [m/s], 0 = use config default
 */
struct bilbo_path_start_cmd_t {
	uint8_t allow_reverse = 0;
	float timeout = 0;
	float max_speed = 0;
};

/**
 * @brief Command for turn-to-heading mode
 */
struct turn_to_heading_command_t {
	uint8_t id;                    // command ID for tracking
	float heading_ref;             // [rad] target heading
	float timeout;                 // [s] command timeout (0 = no timeout)
	float max_angular_speed;   // [rad/s] maximum angular speed (0 = use config)
};

/**
 * @brief Command for drive-to-point mode
 */
struct move_to_point_command_t {
	uint8_t id;                    // command ID for tracking
	float x_target;                // [m] target X position
	float y_target;                // [m] target Y position
	float timeout;                 // [s] command timeout (0 = no timeout)
	float max_speed;             // [m/s] maximum forward speed (0 = use config)
};

/**
 * @brief Controller output (velocity commands)
 */
struct bilbo_position_control_output_t {
	float v_cmd;                    // [m/s] forward velocity command
	float psi_dot_cmd;              // [rad/s] yaw rate command
};

// ============================================================================
// CONFIGURATION
// ============================================================================

/**
 * @brief Configuration parameters for position control
 */
struct bilbo_position_control_config_t {

	// -------------------------------------------------------------------------
	// TIMING
	// -------------------------------------------------------------------------

	float Ts = 0.01f; // [s] Update period. Must match control loop rate (100 Hz = 0.01s)

	// -------------------------------------------------------------------------
	// ANGULAR CONTROL GAINS (heading toward carrot)
	// -------------------------------------------------------------------------

	float kp_angular = 10.0f; // [rad/s per rad] Proportional gain for angular control
	float ki_angular = 0.3f;  // [rad/s per rad*s] Integral gain for angular control

	// -------------------------------------------------------------------------
	// LINEAR CONTROL GAINS (speed toward carrot)
	// -------------------------------------------------------------------------

	float kp_linear = 2.0f;   // [1/s] Proportional gain: speed = kp_linear * carrot_distance
	float ki_linear = 0.0f;   // [1/s^2] Integral gain (usually 0 for path following)

	// -------------------------------------------------------------------------
	// SPEED LIMITS
	// -------------------------------------------------------------------------

	float max_speed = 0.4f;   // [m/s] Maximum forward velocity
	float max_turn_rate = 5.0f;     // [rad/s] Maximum yaw rate
	float speed_transition_time = 0.5f;  // [s] Time to smoothly transition between waypoint speeds

	// -------------------------------------------------------------------------
	// LOOKAHEAD PARAMETERS
	// -------------------------------------------------------------------------

	float lookahead_base = 0.15f;   // [m] Minimum lookahead distance
	float lookahead_gain = 0.3f;    // [s] Lookahead = base + gain * |velocity|
	float lookahead_max = 0.5f;     // [m] Maximum lookahead distance

	// -------------------------------------------------------------------------
	// ARRIVAL AND DWELL
	// -------------------------------------------------------------------------

	float arrival_tolerance = 0.05f; // [m] Distance to consider "arrived"
	float arrival_dwell_time = 0.5f; // [s] Time to hold at STOP waypoint

	// -------------------------------------------------------------------------
	// REVERSE MODE (always enabled)
	// -------------------------------------------------------------------------

	float reverse_enter_angle = 2.1f;  // [rad] ~120 deg - enter reverse mode
	float reverse_exit_angle = 1.05f;  // [rad] ~60 deg - exit reverse mode
};

/**
 * @brief Telemetry and debug data
 */
struct bilbo_position_control_data_t {
	bilbo_position_control_mode_t mode;
	bilbo_path_state_t path_state;

	// Buffer status
	uint16_t buffer_capacity;          // maximum waypoints the buffer can hold
	uint16_t buffer_used;              // current number of waypoints in buffer

	// Path progress
	uint16_t waypoint_count;           // total waypoints in path
	uint16_t current_segment;         // current segment index (0 = start->wp[0])

	// Carrot (lookahead) position
	float carrot_x;                    // [m] current carrot X
	float carrot_y;                    // [m] current carrot Y
	float carrot_distance;             // [m] distance from robot to carrot

	// Control state
	float heading_error;               // [rad] heading error to carrot
	float speed_limit;                 // [m/s] current speed limit

	// Output
	bilbo_position_control_output_t output;

	// Timing
	float elapsed_time;                // [s] time since path started
	float remaining_path_length;       // [m] approximate remaining distance
};

/**
 * @brief Event message data
 */
struct position_control_event_data_t {
	position_control_event_t event;
	bilbo_position_control_data_t data;
	uint32_t tick;
	uint16_t waypoint_index;           // index of waypoint for waypoint events
	uint8_t command_id;                // command ID for single-point commands
};

/**
 * @brief Message type for position control events
 */
typedef BILBO_Message<position_control_event_data_t, MSG_EVENT,
BILBO_MESSAGE_POSITION_CONTROL_EVENT> BILBO_Message_PositionControl_Event;

/**
 * @brief Callback containers for position control events
 */
struct bilbo_position_control_callbacks_t {
	core_utils_CallbackContainer<4, uint16_t> waypoint_passed;    // arg: waypoint index
	core_utils_CallbackContainer<4, uint16_t> waypoint_reached;   // arg: waypoint index
	core_utils_CallbackContainer<4, uint16_t> waypoint_completed; // arg: waypoint index
	core_utils_CallbackContainer<4, uint8_t> path_finished;       // arg: command id
	core_utils_CallbackContainer<4, uint8_t> path_timeout;        // arg: command id
	core_utils_CallbackContainer<4, uint8_t> path_aborted;        // arg: command id
	core_utils_CallbackContainer<4, bilbo_position_control_mode_t> mode_changed; // arg: new mode
};

// ============================================================================
// MAIN CLASS
// ============================================================================

class BILBO_PositionControl {
public:
	static constexpr uint16_t WAYPOINT_BUFFER_SIZE =
			BILBO_POSITION_CONTROL_MAX_WAYPOINTS;

	BILBO_PositionControl();

	// =========================================================================
	// CONFIGURATION
	// =========================================================================

	bool set_config(const bilbo_position_control_config_t &config);
	bilbo_position_control_config_t get_config() const;

	// =========================================================================
	// SINGLE-POINT COMMANDS
	// =========================================================================

	bool turn_to_heading(const turn_to_heading_command_t &command);
	bool move_to_point(const move_to_point_command_t &command);

	// =========================================================================
	// PATH FOLLOWING
	// =========================================================================

	void clear_waypoints();
	bool add_waypoint(const bilbo_waypoint_t &waypoint);
	bool add_waypoint_xy(float x, float y, bilbo_waypoint_type_t type =
			bilbo_waypoint_type_t::PASS, float weight = 0.75f, float speed = 0.0f);
	uint16_t get_waypoint_count() const;
	bilbo_waypoint_t get_current_waypoint() const;

	bool start_path(const bilbo_path_start_cmd_t &command,
			const bilbo_position_state_t &start_state);
	void pause_path();
	void resume_path();
	void abort_path();

	// =========================================================================
	// STATUS
	// =========================================================================

	bilbo_position_control_mode_t get_mode() const;
	bilbo_path_state_t get_path_state() const;
	bilbo_position_control_data_t get_data() const;
	bool is_running() const;
	bool is_idle() const;

	// =========================================================================
	// MAIN UPDATE
	// =========================================================================

	bilbo_position_control_output_t update(
			const bilbo_position_state_t &current_state, float current_v);

	bool reset();

	// =========================================================================
	// CALLBACKS
	// =========================================================================

	bilbo_position_control_callbacks_t callbacks;

	// =========================================================================
	// PUBLIC DATA (for debugging/telemetry)
	// =========================================================================

	bilbo_position_control_mode_t mode;
	bilbo_position_control_config_t config;
	bilbo_position_control_data_t data;

private:
	// =========================================================================
	// ACTIVE COMMANDS
	// =========================================================================

	turn_to_heading_command_t _active_turn_command;
	move_to_point_command_t _active_move_command;
	bilbo_path_start_cmd_t _active_path_command;

	// =========================================================================
	// WAYPOINT BUFFER
	// =========================================================================

	bilbo_waypoint_t _waypoint_buffer[WAYPOINT_BUFFER_SIZE];
	uint16_t _waypoint_count = 0;

	// =========================================================================
	// PATH STATE
	// =========================================================================

	bilbo_path_state_t _path_state = bilbo_path_state_t::IDLE;
	uint16_t _current_segment = 0;         // Index of segment (0 = start->wp[0])

	// Start position (where robot was when path started)
	float _start_x = 0.0f;
	float _start_y = 0.0f;

	// Carrot position (on current segment)
	float _carrot_x = 0.0f;
	float _carrot_y = 0.0f;
	float _carrot_t = 0.0f;    // Parameter [0,1] along current segment

	// =========================================================================
	// PATH GEOMETRY (cached)
	// =========================================================================

	float _segment_lengths[WAYPOINT_BUFFER_SIZE];

	// =========================================================================
	// CONTROL STATE
	// =========================================================================

	float _angular_integral = 0.0f;
	float _linear_integral = 0.0f;
	float _arrival_timer = 0.0f;
	float _elapsed_time = 0.0f;
	bool _reverse_mode_active = false;

	// Speed transition state (for per-waypoint speed limits)
	float _current_speed_limit = 0.0f;    // [m/s] Current smoothed speed limit
	float _target_speed_limit = 0.0f;     // [m/s] Target speed for current waypoint

	// =========================================================================
	// PRIVATE METHODS - PATH GEOMETRY
	// =========================================================================

	void _compute_segment_lengths();
	void _get_segment_points(uint16_t segment_idx, float &ax, float &ay,
			float &bx, float &by) const;
	float _compute_corner_angle_at(uint16_t waypoint_idx) const;

	// =========================================================================
	// PRIVATE METHODS - CARROT ADVANCEMENT
	// =========================================================================

	void _advance_carrot(const bilbo_position_state_t &robot_state,
			float lookahead);
	float _project_robot_to_segment(const bilbo_position_state_t &robot_state,
			uint16_t segment_idx) const;

	// =========================================================================
	// PRIVATE METHODS - CONTROL
	// =========================================================================

	bilbo_position_control_output_t _compute_control(
			const bilbo_position_state_t &robot_state, float current_v);
	float _compute_lookahead(float v) const;

	// =========================================================================
	// PRIVATE METHODS - ARRIVAL/COMPLETION
	// =========================================================================

	bool _check_final_arrival(const bilbo_position_state_t &robot_state);
	void _check_intermediate_stop(const bilbo_position_state_t &robot_state);

	// =========================================================================
	// PRIVATE METHODS - MODE TRANSITIONS
	// =========================================================================

	void _set_mode(bilbo_position_control_mode_t new_mode);

	// =========================================================================
	// PRIVATE METHODS - EVENTS
	// =========================================================================

	void _on_path_started();
	void _on_waypoint_passed(uint16_t waypoint_idx);
	void _on_waypoint_reached(uint16_t waypoint_idx);
	void _on_waypoint_completed(uint16_t waypoint_idx);
	void _on_path_finished();
	void _on_path_timeout();
	void _on_path_aborted();

	void _send_event(position_control_event_t event, uint16_t waypoint_idx = 0);

	// =========================================================================
	// PRIVATE METHODS - MODE-SPECIFIC UPDATES
	// =========================================================================

	bilbo_position_control_output_t _update_follow_path(
			const bilbo_position_state_t &current_state, float current_v);

	bilbo_position_control_output_t _update_turn_to_heading(
			const bilbo_position_state_t &current_state);

	bilbo_position_control_output_t _update_drive_to_point(
			const bilbo_position_state_t &current_state, float current_v);

	// =========================================================================
	// PRIVATE METHODS - UTILITIES
	// =========================================================================

	static float _normalize_angle(float angle);
	static float _distance(float x1, float y1, float x2, float y2);
	static float _clamp(float value, float lo, float hi);
	static float _dot(float ax, float ay, float bx, float by);
};

#endif /* CONTROL_BILBO_POSITION_CONTROL_H_ */
