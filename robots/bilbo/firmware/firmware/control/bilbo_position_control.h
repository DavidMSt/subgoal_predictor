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
 *  3. FOLLOW_PATH:     Follow a dense pre-planned path using pure pursuit
 *
 *  PATH FOLLOWING ALGORITHM (FOLLOW_PATH mode)
 *  ===========================================
 *  Dense path tracking with curvature-based speed:
 *
 *  1. PATH is a dense array of (x,y) points (~15mm uniform spacing)
 *     - Up to 1024 points, with up to 16 explicit STOP indices
 *
 *  2. SPEED derived from path curvature (estimated from upcoming points)
 *     - κ = max Menger curvature in lookahead window
 *     - v_target = max_speed / (1 + curvature_gain * κ)
 *     - Low-pass filtered for smooth transitions
 *     - Deceleration profile near STOP points and path end
 *
 *  3. PURE PURSUIT with adaptive lookahead
 *     - lookahead = v_target / kp_linear (clamped to lookahead_min)
 *     - Carrot placed along path at lookahead distance ahead of robot
 *     - Robot steers toward carrot
 *
 *  4. REVERSE MODE (optional, per path command)
 *     - Robot drives backwards when target is behind it
 *     - Hysteresis prevents oscillation at switching boundary
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
#include "bilbo_estimation.h"
#include "bilbo_message.h"
#include "firmware_addresses.h"

// Maximum number of path points
#define BILBO_POSITION_CONTROL_MAX_PATH_POINTS 1024

// Maximum number of stop indices
#define BILBO_POSITION_CONTROL_MAX_STOPS 16

// Maximum number of points per UART batch
#define BILBO_POSITION_CONTROL_BATCH_SIZE 10

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
	FOLLOW_PATH = 3   // Following dense path
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
	// 1 reserved (was WAYPOINT_PASSED)
	WAYPOINT_REACHED = 2, // Robot within tolerance of STOP point
	WAYPOINT_COMPLETED = 3,   // Dwell finished at STOP point
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
	PATH_BUFFER_FULL = 16   // Path buffer is full
};

// ============================================================================
// DATA STRUCTURES
// ============================================================================

/**
 * @brief Single path point (dense path representation)
 */
struct path_point_t {
	float x;  // [m] world X coordinate
	float y;  // [m] world Y coordinate
};

/**
 * @brief Batch of path points for UART transfer
 *
 * Allows writing up to BATCH_SIZE points at a specific offset in the path buffer.
 * The last batch may have count < BATCH_SIZE.
 */
struct path_points_batch_t {
	uint16_t start_index;  // write offset into _path_buffer
	uint16_t count;        // number of valid points (1..BATCH_SIZE)
	path_point_t points[BILBO_POSITION_CONTROL_BATCH_SIZE];
};

/**
 * @brief Command to start path execution
 *
 * @param max_speed      Speed override [m/s], 0 = use config default
 * @param max_spacing    Maximum inter-point spacing [m], 0 = auto-detect from path
 * @param timeout        Maximum time for path execution [s], 0 = no timeout
 * @param allow_reverse  If non-zero, robot may drive backwards when more efficient
 */
struct bilbo_path_start_cmd_t {
	float max_speed = 0.0f;
	float max_spacing = 0.0f;
	float timeout = 0.0f;
	uint8_t allow_reverse = 0;
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

	float kp_linear = 2.0f;   // [1/s] Proportional gain: speed = kp_linear * carrot_distance (fallback when decel_limit=0)
	float ki_linear = 0.0f;   // [1/s^2] Integral gain (usually 0 for path following)
	float kd_linear = 0.5f;   // [-] Velocity damping: subtracts kd_linear * |current_v| from speed command

	// -------------------------------------------------------------------------
	// SPEED LIMITS
	// -------------------------------------------------------------------------

	float max_speed = 0.5f;   // [m/s] Maximum forward velocity
	float max_turn_rate = 5.0f;     // [rad/s] Maximum yaw rate

	// -------------------------------------------------------------------------
	// LOOKAHEAD PARAMETERS
	// -------------------------------------------------------------------------

	float lookahead_base = 0.15f;   // [m] Base lookahead distance (used by move_to_point)
	float lookahead_min = 0.03f;    // [m] Minimum lookahead distance for path following

	// -------------------------------------------------------------------------
	// ARRIVAL AND DWELL
	// -------------------------------------------------------------------------

	float arrival_tolerance = 0.05f; // [m] Distance to consider "arrived"
	float arrival_dwell_time = 0.5f; // [s] Time to hold at path end
	float stop_dwell_time = 1.0f;   // [s] Time to hold at STOP waypoints (separate from path end)

	// -------------------------------------------------------------------------
	// REVERSE MODE
	// -------------------------------------------------------------------------

	float reverse_enter_angle = 2.1f;  // [rad] ~120 deg - enter reverse mode
	float reverse_exit_angle = 1.05f;  // [rad] ~60 deg - exit reverse mode

	// -------------------------------------------------------------------------
	// DECELERATION
	// -------------------------------------------------------------------------

	float decel_limit = 0.0f;  // [m/s^2] Max deceleration for sqrt profile. 0 = disabled (use linear kp*d)

	// -------------------------------------------------------------------------
	// CURVATURE-BASED SPEED (path following)
	// -------------------------------------------------------------------------

	float curvature_gain = 2.0f;       // [-] Curvature sensitivity: v = max_speed / (1 + gain * κ). Higher = slower in curves.
	float curvature_lookahead = 0.3f;  // [m] How far ahead to estimate curvature (0 = use current segment only)
};

/**
 * @brief Telemetry and debug data
 */
struct bilbo_position_control_data_t {
	bilbo_position_control_mode_t mode;
	bilbo_path_state_t path_state;

	// Buffer status
	uint16_t buffer_capacity;          // maximum path points the buffer can hold
	uint16_t buffer_used;              // current number of path points in buffer

	// Path progress
	uint16_t path_point_count;         // total path points in path
	uint16_t current_index;            // current path index (floor of progress)

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

	// Dense path progress
	float progress;                    // floating-point index [0, N-1]
};

/**
 * @brief Event message data
 */
struct position_control_event_data_t {
	position_control_event_t event;
	bilbo_position_control_data_t data;
	uint32_t tick;
	uint16_t waypoint_index;           // index of path point for stop events
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
	core_utils_CallbackContainer<4, uint16_t> stop_reached;     // arg: path index
	core_utils_CallbackContainer<4, uint16_t> stop_completed;   // arg: path index
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
	static constexpr uint16_t PATH_BUFFER_SIZE =
			BILBO_POSITION_CONTROL_MAX_PATH_POINTS;
	static constexpr uint8_t MAX_STOPS =
			BILBO_POSITION_CONTROL_MAX_STOPS;

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
	// PATH MANAGEMENT
	// =========================================================================

	void clear_path();
	bool add_path_point(float x, float y);
	bool add_path_points_batch(const path_points_batch_t &batch);
	bool set_path(const path_point_t *pts, uint16_t count);
	bool add_stop_index(uint16_t index);
	uint16_t get_path_point_count() const;

	/**
	 * @brief Handle path data received via SPI DMA.
	 *
	 * Clears the existing path and copies data from the SPI receive buffer.
	 *
	 * @param spi_buffer Pointer to the SPI receive buffer containing path_point_t data.
	 * @param count Number of path points received.
	 */
	void spiPathReceived(const path_point_t *spi_buffer, uint16_t count);

	bool start_path(const bilbo_path_start_cmd_t &command);
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
	// PATH BUFFER
	// =========================================================================

	path_point_t _path_buffer[PATH_BUFFER_SIZE];     // 8 KB
	float _cumul_dist[PATH_BUFFER_SIZE];             // 4 KB (precomputed at start)
	uint16_t _stop_indices[MAX_STOPS];               // 32 B
	uint16_t _path_count = 0;
	uint8_t _stop_count = 0;

	// =========================================================================
	// PATH STATE
	// =========================================================================

	bilbo_path_state_t _path_state = bilbo_path_state_t::IDLE;

	float _progress = 0.0f;             // floating-point index [0, N-1]
	float _path_max_speed = 0.0f;       // resolved max speed for this path
	float _path_max_spacing = 0.0f;     // max inter-point spacing
	float _path_total_length = 0.0f;    // total arc length
	uint8_t _next_stop_ptr = 0;         // index into _stop_indices

	// Carrot position
	float _carrot_x = 0.0f;
	float _carrot_y = 0.0f;

	// =========================================================================
	// CONTROL STATE
	// =========================================================================

	float _angular_integral = 0.0f;
	float _linear_integral = 0.0f;
	float _arrival_timer = 0.0f;
	float _elapsed_time = 0.0f;
	bool _reverse_mode_active = false;

	// STOP point event tracking
	bool _stop_reached_sent = false;

	// Smoothed speed target (low-pass filtered to avoid step changes)
	float _v_target_smooth = 0.0f;

	// =========================================================================
	// PRIVATE METHODS - PATH GEOMETRY
	// =========================================================================

	void _compute_cumulative_distances();

	// =========================================================================
	// PRIVATE METHODS - PATH TRACKING HELPERS
	// =========================================================================

	float _project_onto_path(float robot_x, float robot_y, float last_progress) const;
	float _advance_along_path(float from_progress, float distance_meters) const;
	void _interpolate_path(float progress, float &out_x, float &out_y) const;
	float _cumul_dist_at(float progress) const;
	float _estimate_curvature_ahead(float at_progress, float lookahead_dist) const;

	// =========================================================================
	// PRIVATE METHODS - MODE TRANSITIONS
	// =========================================================================

	void _set_mode(bilbo_position_control_mode_t new_mode);

	// =========================================================================
	// PRIVATE METHODS - EVENTS
	// =========================================================================

	void _on_path_started();
	void _on_stop_reached(uint16_t path_idx);
	void _on_stop_completed(uint16_t path_idx);
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
