/*
 * bilbo_position_control.cpp
 *
 *  Created on: Jan 25, 2026
 *      Author: lehmann
 *
 *  SIMPLIFIED PATH FOLLOWING IMPLEMENTATION
 *  ========================================
 *
 *  Key design principles (practical, tested in real-world):
 *
 *  1. DECOUPLED SPEED AND STEERING
 *     - Speed = kp_linear * max(dist_to_waypoint, carrot_dist)
 *     - Steering = heading toward carrot (where to steer)
 *     - Maintains speed through PASS waypoints (carrot advances freely)
 *     - Slows at tight corners (carrot blocked by weight+angle)
 *     - Slows at STOP waypoints (carrot stays at waypoint)
 *
 *  2. CARROT ON SEGMENTS (for steering only)
 *     - Carrot always stays on the line between waypoints
 *     - Cannot go backward on current segment
 *     - Small lookahead = tight path following
 *     - Advancing to next segment depends on weight + corner angle
 *
 *  3. WEIGHT + ANGLE for corners
 *     - effective_weight = weight * (corner_angle / PI)
 *     - Straight path (angle=0): carrot advances freely regardless of weight
 *     - Sharp corner (angle=PI): full weight effect
 *
 *  4. REVERSE MODE always enabled
 *     - Robot can drive backwards when target is behind
 *     - Hysteresis prevents oscillation
 */

#include "bilbo_position_control.h"
#include <cstring>
#include "twipr_communication.h"

#ifndef M_PI
#define M_PI 3.14159265358979323846f
#endif

static constexpr float EPSILON = 1e-6f;

// ============================================================================
// CONSTRUCTOR
// ============================================================================

BILBO_PositionControl::BILBO_PositionControl() {
	mode = bilbo_position_control_mode_t::IDLE;
	_path_state = bilbo_path_state_t::IDLE;
	_waypoint_count = 0;
	_current_segment = 0;
	_reverse_mode_active = false;

	memset(_waypoint_buffer, 0, sizeof(_waypoint_buffer));
	memset(_segment_lengths, 0, sizeof(_segment_lengths));
}

// ============================================================================
// CONFIGURATION
// ============================================================================

bool BILBO_PositionControl::set_config(const bilbo_position_control_config_t& cfg) {
	if (cfg.Ts <= 0.0f) return false;
	if (cfg.max_speed <= 0.0f) return false;
	if (cfg.max_turn_rate <= 0.0f) return false;

	config = cfg;
	return true;
}

bilbo_position_control_config_t BILBO_PositionControl::get_config() const {
	return config;
}

// ============================================================================
// SINGLE-POINT COMMANDS
// ============================================================================

bool BILBO_PositionControl::turn_to_heading(const turn_to_heading_command_t& command) {
	if (mode != bilbo_position_control_mode_t::IDLE) {
		return false;
	}

	_active_turn_command = command;
	_elapsed_time = 0.0f;
	_angular_integral = 0.0f;
	_arrival_timer = 0.0f;

	_set_mode(bilbo_position_control_mode_t::TURN_TO_HEADING);
	_send_event(position_control_event_t::TURN_TO_HEADING_STARTED);
	return true;
}

bool BILBO_PositionControl::move_to_point(const move_to_point_command_t& command) {
	if (mode != bilbo_position_control_mode_t::IDLE) {
		return false;
	}

	_active_move_command = command;
	_elapsed_time = 0.0f;
	_angular_integral = 0.0f;
	_linear_integral = 0.0f;
	_arrival_timer = 0.0f;
	_reverse_mode_active = false;

	_set_mode(bilbo_position_control_mode_t::DRIVE_TO_POINT);
	_send_event(position_control_event_t::MOVE_TO_POINT_STARTED);
	return true;
}

// ============================================================================
// PATH FOLLOWING - WAYPOINT MANAGEMENT
// ============================================================================

void BILBO_PositionControl::clear_waypoints() {
	_waypoint_count = 0;
	_path_state = bilbo_path_state_t::IDLE;
	_current_segment = 0;
	_carrot_t = 0.0f;
	_angular_integral = 0.0f;
	_linear_integral = 0.0f;
	_arrival_timer = 0.0f;
	_reverse_mode_active = false;
	_current_speed_limit = 0.0f;
	_target_speed_limit = 0.0f;
	_waypoint_reached_sent = false;

	memset(_segment_lengths, 0, sizeof(_segment_lengths));
}

bool BILBO_PositionControl::add_waypoint(const bilbo_waypoint_t& waypoint) {
	if (_waypoint_count >= WAYPOINT_BUFFER_SIZE) {
		_send_event(position_control_event_t::WAYPOINT_BUFFER_FULL);
		return false;
	}

	_waypoint_buffer[_waypoint_count] = waypoint;
	_waypoint_count++;
	return true;
}

bool BILBO_PositionControl::add_waypoint_xy(float x, float y,
                                            bilbo_waypoint_type_t type,
                                            float weight,
                                            float speed) {
	bilbo_waypoint_t wp;
	wp.x = x;
	wp.y = y;
	wp.type = type;
	wp.weight = _clamp(weight, 0.0f, 1.0f);
	wp.speed = (speed > 0.0f) ? speed : 0.0f;  // 0 means use path default
	return add_waypoint(wp);
}

uint16_t BILBO_PositionControl::get_waypoint_count() const {
	return _waypoint_count;
}

bilbo_waypoint_t BILBO_PositionControl::get_current_waypoint() const {
	bilbo_waypoint_t wp = {0.0f, 0.0f, bilbo_waypoint_type_t::PASS, 0.0f};

	if (_waypoint_count > 0 && _current_segment < _waypoint_count) {
		wp = _waypoint_buffer[_current_segment];
	}

	return wp;
}

// ============================================================================
// PATH FOLLOWING - EXECUTION CONTROL
// ============================================================================

bool BILBO_PositionControl::start_path(const bilbo_path_start_cmd_t& command,
                                       const bilbo_position_state_t& start_state) {
	if (_waypoint_count == 0) {
		return false;
	}

	if (mode != bilbo_position_control_mode_t::IDLE) {
		return false;
	}

	// Store start position
	_start_x = start_state.x;
	_start_y = start_state.y;

	// Initialize carrot at start
	_carrot_x = start_state.x;
	_carrot_y = start_state.y;
	_carrot_t = 0.0f;

	// Compute segment lengths
	_compute_segment_lengths();

	// Initialize state
	_current_segment = 0;
	_angular_integral = 0.0f;
	_linear_integral = 0.0f;
	_arrival_timer = 0.0f;
	_elapsed_time = 0.0f;
	_reverse_mode_active = false;
	_waypoint_reached_sent = false;

	// Initialize speed limits based on first waypoint
	float path_max_speed = (command.max_speed > 0.0f) ? command.max_speed : config.max_speed;
	float first_wp_speed = _waypoint_buffer[0].speed;
	_target_speed_limit = (first_wp_speed > 0.0f) ? first_wp_speed : path_max_speed;
	_current_speed_limit = _target_speed_limit;  // Start at target (no ramp at path start)

	// Store command
	_active_path_command = command;

	// Set mode and state
	_path_state = bilbo_path_state_t::RUNNING;
	_set_mode(bilbo_position_control_mode_t::FOLLOW_PATH);

	_on_path_started();
	return true;
}

void BILBO_PositionControl::pause_path() {
	if (_path_state == bilbo_path_state_t::RUNNING) {
		_path_state = bilbo_path_state_t::PAUSED;
		_send_event(position_control_event_t::PATH_PAUSED);
	}
}

void BILBO_PositionControl::resume_path() {
	if (_path_state == bilbo_path_state_t::PAUSED) {
		_path_state = bilbo_path_state_t::RUNNING;
		_send_event(position_control_event_t::PATH_RESUMED);
	}
}

void BILBO_PositionControl::abort_path() {
	if (mode == bilbo_position_control_mode_t::FOLLOW_PATH) {
		_on_path_aborted();
		_path_state = bilbo_path_state_t::IDLE;
		_set_mode(bilbo_position_control_mode_t::IDLE);
	}
}

// ============================================================================
// STATUS QUERIES
// ============================================================================

bilbo_position_control_mode_t BILBO_PositionControl::get_mode() const {
	return mode;
}

bilbo_path_state_t BILBO_PositionControl::get_path_state() const {
	return _path_state;
}

bilbo_position_control_data_t BILBO_PositionControl::get_data() const {
	return data;
}

bool BILBO_PositionControl::is_running() const {
	return _path_state == bilbo_path_state_t::RUNNING;
}

bool BILBO_PositionControl::is_idle() const {
	return mode == bilbo_position_control_mode_t::IDLE;
}

bool BILBO_PositionControl::reset() {
	// Send termination events if a command was active (e.g., due to control mode change)
	switch (mode) {
	case bilbo_position_control_mode_t::FOLLOW_PATH:
		_on_path_aborted();
		_path_state = bilbo_path_state_t::IDLE;
		break;
	case bilbo_position_control_mode_t::DRIVE_TO_POINT:
		_send_event(position_control_event_t::MOVE_TO_POINT_TIMEOUT);
		break;
	case bilbo_position_control_mode_t::TURN_TO_HEADING:
		_send_event(position_control_event_t::TURN_TO_HEADING_TIMEOUT);
		break;
	default:
		break;
	}

	_angular_integral = 0.0f;
	_linear_integral = 0.0f;
	_arrival_timer = 0.0f;
	_elapsed_time = 0.0f;
	_reverse_mode_active = false;
	_current_speed_limit = 0.0f;
	_target_speed_limit = 0.0f;
	this->clear_waypoints();
	this->_set_mode(bilbo_position_control_mode_t::IDLE);
	return true;
}

// ============================================================================
// MAIN UPDATE
// ============================================================================

bilbo_position_control_output_t BILBO_PositionControl::update(
		const bilbo_position_state_t& current_state,
		float current_v) {

	bilbo_position_control_output_t output = {0.0f, 0.0f};

	if (mode != bilbo_position_control_mode_t::IDLE) {
		_elapsed_time += config.Ts;
	}

	switch (mode) {
	case bilbo_position_control_mode_t::IDLE:
		break;

	case bilbo_position_control_mode_t::TURN_TO_HEADING:
		output = _update_turn_to_heading(current_state);
		break;

	case bilbo_position_control_mode_t::DRIVE_TO_POINT:
		output = _update_drive_to_point(current_state, current_v);
		break;

	case bilbo_position_control_mode_t::FOLLOW_PATH:
		output = _update_follow_path(current_state, current_v);
		break;
	}

	// Update telemetry
	data.mode = mode;
	data.path_state = _path_state;
	data.buffer_capacity = WAYPOINT_BUFFER_SIZE;
	data.buffer_used = _waypoint_count;
	data.output = output;
	data.elapsed_time = _elapsed_time;

	return output;
}

// ============================================================================
// PATH FOLLOWING UPDATE
// ============================================================================

bilbo_position_control_output_t BILBO_PositionControl::_update_follow_path(
		const bilbo_position_state_t& current_state,
		float current_v) {

	bilbo_position_control_output_t output = {0.0f, 0.0f};

	if (_path_state != bilbo_path_state_t::RUNNING || _waypoint_count == 0) {
		return output;
	}

	// Check timeout
	if (_active_path_command.timeout > 0.0f &&
		_elapsed_time > _active_path_command.timeout) {
		_on_path_timeout();
		_path_state = bilbo_path_state_t::IDLE;
		_set_mode(bilbo_position_control_mode_t::IDLE);
		return output;
	}

	// Check final arrival
	if (_check_final_arrival(current_state)) {
		_on_path_finished();
		_path_state = bilbo_path_state_t::IDLE;
		_set_mode(bilbo_position_control_mode_t::IDLE);
		return output;
	}

	// Compute lookahead distance
	float lookahead = _compute_lookahead(current_v);

	// Advance carrot along path
	_advance_carrot(current_state, lookahead);

	// Compute control output
	output = _compute_control(current_state, current_v);

	// Check intermediate STOP waypoints
	_check_intermediate_stop(current_state);

	// Update telemetry
	data.waypoint_count = _waypoint_count;
	data.current_segment = _current_segment;
	data.carrot_x = _carrot_x;
	data.carrot_y = _carrot_y;

	return output;
}

// ============================================================================
// PATH GEOMETRY METHODS
// ============================================================================

void BILBO_PositionControl::_compute_segment_lengths() {
	for (uint16_t i = 0; i < _waypoint_count; i++) {
		float ax, ay, bx, by;
		_get_segment_points(i, ax, ay, bx, by);
		_segment_lengths[i] = _distance(ax, ay, bx, by);
	}
}

void BILBO_PositionControl::_get_segment_points(uint16_t segment_idx,
                                                float& ax, float& ay,
                                                float& bx, float& by) const {
	if (segment_idx == 0) {
		ax = _start_x;
		ay = _start_y;
	} else {
		ax = _waypoint_buffer[segment_idx - 1].x;
		ay = _waypoint_buffer[segment_idx - 1].y;
	}

	bx = _waypoint_buffer[segment_idx].x;
	by = _waypoint_buffer[segment_idx].y;
}

/**
 * Compute corner angle at a waypoint.
 * Returns angle in [0, PI]: 0 = straight, PI = U-turn
 */
float BILBO_PositionControl::_compute_corner_angle_at(uint16_t waypoint_idx) const {
	if (waypoint_idx >= _waypoint_count - 1) {
		return 0.0f;  // Last waypoint has no outgoing segment
	}

	// Incoming vector: previous -> this waypoint
	float ax, ay, bx, by;
	_get_segment_points(waypoint_idx, ax, ay, bx, by);
	float v1x = bx - ax;
	float v1y = by - ay;

	// Outgoing vector: this waypoint -> next
	const bilbo_waypoint_t& next_wp = _waypoint_buffer[waypoint_idx + 1];
	float v2x = next_wp.x - bx;
	float v2y = next_wp.y - by;

	// Compute angle between vectors
	float mag1 = sqrtf(v1x * v1x + v1y * v1y);
	float mag2 = sqrtf(v2x * v2x + v2y * v2y);

	if (mag1 < EPSILON || mag2 < EPSILON) {
		return 0.0f;
	}

	float dot = v1x * v2x + v1y * v2y;
	float cos_angle = _clamp(dot / (mag1 * mag2), -1.0f, 1.0f);

	return acosf(cos_angle);  // [0, PI]
}

// ============================================================================
// CARROT ADVANCEMENT
// ============================================================================

/**
 * Project robot position onto a segment and return t parameter [0,1]
 */
float BILBO_PositionControl::_project_robot_to_segment(
		const bilbo_position_state_t& robot_state,
		uint16_t segment_idx) const {

	float ax, ay, bx, by;
	_get_segment_points(segment_idx, ax, ay, bx, by);

	float dx = bx - ax;
	float dy = by - ay;
	float len_sq = dx * dx + dy * dy;

	if (len_sq < EPSILON) {
		return 1.0f;  // Degenerate segment
	}

	float t = ((robot_state.x - ax) * dx + (robot_state.y - ay) * dy) / len_sq;
	return _clamp(t, 0.0f, 1.0f);
}

/**
 * Advance carrot along the path.
 *
 * Key algorithm:
 * 1. Project robot onto current segment
 * 2. Place carrot at robot_t + lookahead/segment_length
 * 3. If carrot wants to go past waypoint, check weight + corner angle
 * 4. Carrot can never go backward
 */
void BILBO_PositionControl::_advance_carrot(
		const bilbo_position_state_t& robot_state,
		float lookahead) {

	if (_current_segment >= _waypoint_count) {
		return;
	}

	// Get current segment info
	float ax, ay, bx, by;
	_get_segment_points(_current_segment, ax, ay, bx, by);
	float seg_len = _segment_lengths[_current_segment];

	// Project robot onto segment
	float robot_t = _project_robot_to_segment(robot_state, _current_segment);

	// Convert lookahead to t-parameter
	float lookahead_t = (seg_len > EPSILON) ? (lookahead / seg_len) : 1.0f;

	// Desired carrot position
	float desired_t = robot_t + lookahead_t;

	// Check if carrot wants to advance past current waypoint
	if (desired_t >= 1.0f && _current_segment < _waypoint_count - 1) {
		const bilbo_waypoint_t& wp = _waypoint_buffer[_current_segment];
		bool is_stop = (wp.type == bilbo_waypoint_type_t::STOP);

		if (is_stop) {
			// STOP waypoint: carrot stays at waypoint until robot arrives
			desired_t = 1.0f;
		} else {
			// PASS waypoint: weight + corner angle determines advancement

			// Compute corner angle (skip for segment 0 - the "incoming" direction
			// from arbitrary start position is not part of the designed path)
			float angle_factor = 0.0f;
			if (_current_segment > 0) {
				float corner_angle = _compute_corner_angle_at(_current_segment);
				// Effective weight: weight is modulated by corner sharpness
				// - Straight path (angle=0): effective_weight = 0 (free advancement)
				// - Sharp corner (angle=PI): effective_weight = full weight
				// Using sqrt for less aggressive modulation - allows user weight to have
				// more effect even on moderate corners (e.g., 30° corner: sqrt(0.1)=0.32 vs 0.1)
				angle_factor = sqrtf(corner_angle / M_PI);  // [0, 1], sqrt for gentler modulation
			}
			float effective_weight = wp.weight * angle_factor;

			// Distance robot needs to be from waypoint before carrot can advance
			float robot_threshold = (1.0f - effective_weight) * lookahead;
			float robot_dist_to_wp = _distance(robot_state.x, robot_state.y,
			                                   wp.x, wp.y);

			if (robot_dist_to_wp > robot_threshold) {
				// Robot too far: carrot stops at waypoint
				desired_t = 1.0f;
			} else {
				// Robot close enough: advance to next segment
				float overshoot = desired_t - 1.0f;
				_on_waypoint_passed(_current_segment);
				_current_segment++;
				_angular_integral = 0.0f;  // Reset integrator for new segment

				if (_current_segment < _waypoint_count) {
					// Continue on next segment
					float next_seg_len = _segment_lengths[_current_segment];
					_carrot_t = (next_seg_len > EPSILON) ?
						(overshoot * seg_len / next_seg_len) : 0.0f;
					_carrot_t = _clamp(_carrot_t, 0.0f, 1.0f);

					// Update segment points for carrot calculation
					_get_segment_points(_current_segment, ax, ay, bx, by);
					_carrot_x = ax + _carrot_t * (bx - ax);
					_carrot_y = ay + _carrot_t * (by - ay);
					return;
				}
			}
		}
	}

	// Carrot can never go backward on current segment
	_carrot_t = fmaxf(_carrot_t, _clamp(desired_t, 0.0f, 1.0f));

	// Compute carrot XY
	_carrot_x = ax + _carrot_t * (bx - ax);
	_carrot_y = ay + _carrot_t * (by - ay);
}

// ============================================================================
// CONTROL OUTPUT
// ============================================================================

float BILBO_PositionControl::_compute_lookahead(float v) const {
	float lookahead = config.lookahead_base +
	                  config.lookahead_gain * fabsf(v);
	return _clamp(lookahead, config.lookahead_base, config.lookahead_max);
}

/**
 * Compute velocity and yaw rate commands.
 *
 * Key features:
 * 1. Speed = kp_linear * max(dist_to_waypoint, carrot_dist)
 *    - Maintains speed through PASS waypoints when carrot advances
 *    - Slows at tight corners (carrot can't advance due to weight+angle)
 *    - Slows at STOP waypoints (carrot stays at waypoint)
 * 2. Heading toward carrot (small lookahead = tight path following)
 * 3. Reverse mode with hysteresis (always enabled)
 * 4. cos(heading_error) speed scaling
 * 5. PI angular control with anti-windup
 */
bilbo_position_control_output_t BILBO_PositionControl::_compute_control(
		const bilbo_position_state_t& robot_state,
		float current_v) {

	bilbo_position_control_output_t output = {0.0f, 0.0f};

	// Distance and angle to carrot (for steering)
	float dx_carrot = _carrot_x - robot_state.x;
	float dy_carrot = _carrot_y - robot_state.y;
	float carrot_dist = sqrtf(dx_carrot * dx_carrot + dy_carrot * dy_carrot);
	float angle_to_carrot = atan2f(dy_carrot, dx_carrot);

	// Distance to current target waypoint
	const bilbo_waypoint_t& target_wp = _waypoint_buffer[_current_segment];
	float dist_to_waypoint = _distance(robot_state.x, robot_state.y,
	                                   target_wp.x, target_wp.y);

	// Speed distance: use the larger of carrot_dist and dist_to_waypoint
	// - Keeps speed up when carrot advances past PASS waypoints
	// - Slows down at tight corners (carrot blocked by weight+angle)
	// - Slows down at STOP waypoints (carrot stays at waypoint)
	float speed_dist = fmaxf(carrot_dist, dist_to_waypoint);

	// Heading error to carrot (forward)
	float heading_error_fwd = _normalize_angle(angle_to_carrot - robot_state.psi);

	// -------------------------------------------------------------------------
	// Reverse mode with hysteresis (always enabled)
	// -------------------------------------------------------------------------

	float abs_heading_error = fabsf(heading_error_fwd);

	if (!_reverse_mode_active && abs_heading_error > config.reverse_enter_angle) {
		_reverse_mode_active = true;
		_angular_integral = 0.0f;  // Reset on mode switch
	} else if (_reverse_mode_active && abs_heading_error < config.reverse_exit_angle) {
		_reverse_mode_active = false;
		_angular_integral = 0.0f;  // Reset on mode switch
	}

	// In reverse mode, flip the target heading
	float heading_error = heading_error_fwd;
	if (_reverse_mode_active) {
		heading_error = _normalize_angle(heading_error_fwd + M_PI);
	}

	data.heading_error = heading_error;
	data.carrot_distance = carrot_dist;

	// -------------------------------------------------------------------------
	// Velocity command: v = kp_linear * speed_dist
	// -------------------------------------------------------------------------

	// Determine path-level max speed
	float path_max_speed = config.max_speed;
	if (_active_path_command.max_speed > 0.0f) {
		path_max_speed = fminf(path_max_speed, _active_path_command.max_speed);
	}

	// Get per-waypoint speed target (0 = use path default)
	float wp_speed = target_wp.speed;
	_target_speed_limit = (wp_speed > 0.0f) ? fminf(wp_speed, path_max_speed) : path_max_speed;

	// Smooth transition to target speed over config.speed_transition_time
	// Rate = (target - current) / transition_time, clamped for stability
	if (config.speed_transition_time > EPSILON) {
		float speed_diff = _target_speed_limit - _current_speed_limit;
		float max_rate = path_max_speed / config.speed_transition_time;  // Max change per second
		float rate = _clamp(speed_diff / config.speed_transition_time, -max_rate, max_rate);
		_current_speed_limit += rate * config.Ts;
		_current_speed_limit = _clamp(_current_speed_limit, 0.0f, path_max_speed);
	} else {
		_current_speed_limit = _target_speed_limit;  // Instant transition
	}

	// Corner angle slowdown: reduce speed based on upcoming corner sharpness
	// Only applies when approaching the corner, not the entire segment.
	//
	// NOTE: Skip segment 0 because the "incoming" direction (from arbitrary start
	// position to first waypoint) is not part of the designed path.
	float corner_speed_factor = 1.0f;
	if (_current_segment > 0 && _current_segment < _waypoint_count - 1) {
		float corner_angle = _compute_corner_angle_at(_current_segment);
		// Factor: 1.0 for straight (angle=0), decreasing for sharper corners
		// Using cosine for smooth transition: cos(0)=1, cos(PI)=-1
		// Map to [0.3, 1.0] range: even sharp corners allow some speed
		float cos_angle = cosf(corner_angle);  // [-1, 1]
		float full_corner_factor = 0.65f + 0.35f * cos_angle;  // [0.3, 1.0]
		full_corner_factor = _clamp(full_corner_factor, 0.3f, 1.0f);

		// Fade in slowdown as we approach the corner
		// - Far from corner: no slowdown (factor = 1.0)
		// - At corner: full slowdown based on angle
		float fade = _clamp(1.0f - dist_to_waypoint / config.corner_slowdown_distance, 0.0f, 1.0f);
		// fade = 0 when far, 1 when close

		// Interpolate between 1.0 (no slowdown) and full_corner_factor
		corner_speed_factor = 1.0f - fade * (1.0f - full_corner_factor);
	}

	// Effective max speed: minimum of smoothed waypoint limit and corner factor
	float max_speed = _current_speed_limit * corner_speed_factor;

	// Velocity profile: sqrt deceleration curve when decel_limit set, else linear kp*d
	float v_p;
	if (config.decel_limit > 0.0f && speed_dist > 0.0f) {
		v_p = sqrtf(2.0f * config.decel_limit * speed_dist);
	} else {
		v_p = config.kp_linear * speed_dist;
	}

	// Velocity damping: prevent overshoot by braking when already moving
	v_p = fmaxf(0.0f, v_p - config.kd_linear * fabsf(current_v));

	float v_i = _linear_integral;
	float v_unsat = v_p + v_i;
	float v_sat = _clamp(v_unsat, 0.0f, max_speed);

	// Anti-windup for linear integral
	if (fabsf(v_unsat - v_sat) < EPSILON) {
		_linear_integral += config.ki_linear * speed_dist * config.Ts;
		_linear_integral = _clamp(_linear_integral, 0.0f, max_speed);
	}

	// Scale by cos(heading_error) - slow down when not facing carrot
	float cos_scale = fmaxf(0.0f, cosf(heading_error));
	float v_cmd = v_sat * cos_scale;

	// Reverse mode: negate velocity
	if (_reverse_mode_active) {
		v_cmd = -v_cmd;
	}

	output.v_cmd = v_cmd;
	data.speed_limit = v_sat;

	// -------------------------------------------------------------------------
	// Angular command: PI control on heading error
	// -------------------------------------------------------------------------

	float w_p = config.kp_angular * heading_error;
	float w_i = _angular_integral;
	float w_unsat = w_p + w_i;
	float w_sat = _clamp(w_unsat, -config.max_turn_rate, config.max_turn_rate);

	// Anti-windup
	bool is_saturated = fabsf(w_unsat - w_sat) > EPSILON;
	bool would_push_further = is_saturated && (
		(w_unsat > w_sat && heading_error > 0.0f) ||
		(w_unsat < w_sat && heading_error < 0.0f));

	if (!would_push_further) {
		_angular_integral += config.ki_angular * heading_error * config.Ts;
		float max_integral = config.max_turn_rate / fmaxf(config.ki_angular, 0.01f);
		_angular_integral = _clamp(_angular_integral, -max_integral, max_integral);
	}

	// Fade yaw rate near arrival to prevent jitter
	float fade_radius = 2.0f * config.arrival_tolerance;
	float w_fade = _clamp(speed_dist / fade_radius, 0.0f, 1.0f);

	output.psi_dot_cmd = w_sat * w_fade;

	return output;
}

// ============================================================================
// ARRIVAL / COMPLETION
// ============================================================================

bool BILBO_PositionControl::_check_final_arrival(
		const bilbo_position_state_t& robot_state) {

	if (_current_segment < _waypoint_count - 1) {
		return false;
	}

	const bilbo_waypoint_t& final_wp = _waypoint_buffer[_waypoint_count - 1];
	float dist = _distance(robot_state.x, robot_state.y, final_wp.x, final_wp.y);

	if (dist < config.arrival_tolerance) {
		_arrival_timer += config.Ts;
		if (_arrival_timer >= config.arrival_dwell_time) {
			return true;
		}
	} else {
		_arrival_timer = 0.0f;
	}

	return false;
}

void BILBO_PositionControl::_check_intermediate_stop(
		const bilbo_position_state_t& robot_state) {

	if (_current_segment >= _waypoint_count - 1) {
		return;  // Handled by _check_final_arrival
	}

	const bilbo_waypoint_t& wp = _waypoint_buffer[_current_segment];

	if (wp.type != bilbo_waypoint_type_t::STOP) {
		return;
	}

	float dist = _distance(robot_state.x, robot_state.y, wp.x, wp.y);

	if (dist < config.arrival_tolerance) {
		// Only send WAYPOINT_REACHED event once when first entering tolerance
		if (!_waypoint_reached_sent) {
			_on_waypoint_reached(_current_segment);
			_waypoint_reached_sent = true;
		}

		_arrival_timer += config.Ts;
		if (_arrival_timer >= config.arrival_dwell_time) {
			_on_waypoint_completed(_current_segment);
			_current_segment++;
			_carrot_t = 0.0f;
			_arrival_timer = 0.0f;
			_angular_integral = 0.0f;
			_waypoint_reached_sent = false;  // Reset for next STOP waypoint
		}
	} else {
		_arrival_timer = 0.0f;
		_waypoint_reached_sent = false;  // Reset if robot leaves tolerance zone
	}
}

// ============================================================================
// MODE TRANSITIONS
// ============================================================================

void BILBO_PositionControl::_set_mode(bilbo_position_control_mode_t new_mode) {
	if (mode != new_mode) {
		mode = new_mode;
		_send_event(position_control_event_t::MODE_CHANGED);
		callbacks.mode_changed.call(new_mode);
	}
}

// ============================================================================
// EVENT HANDLERS
// ============================================================================

void BILBO_PositionControl::_on_path_started() {
	_send_event(position_control_event_t::PATH_STARTED);
}

void BILBO_PositionControl::_on_waypoint_passed(uint16_t waypoint_idx) {
	_send_event(position_control_event_t::WAYPOINT_PASSED, waypoint_idx);
	callbacks.waypoint_passed.call(waypoint_idx);
}

void BILBO_PositionControl::_on_waypoint_reached(uint16_t waypoint_idx) {
	_send_event(position_control_event_t::WAYPOINT_REACHED, waypoint_idx);
	callbacks.waypoint_reached.call(waypoint_idx);
}

void BILBO_PositionControl::_on_waypoint_completed(uint16_t waypoint_idx) {
	_send_event(position_control_event_t::WAYPOINT_COMPLETED, waypoint_idx);
	callbacks.waypoint_completed.call(waypoint_idx);
}

void BILBO_PositionControl::_on_path_finished() {
	_send_event(position_control_event_t::PATH_FINISHED);
	callbacks.path_finished.call(0);
}

void BILBO_PositionControl::_on_path_timeout() {
	_send_event(position_control_event_t::PATH_TIMEOUT);
	callbacks.path_timeout.call(0);
}

void BILBO_PositionControl::_on_path_aborted() {
	_send_event(position_control_event_t::PATH_ABORTED);
	callbacks.path_aborted.call(0);
}

void BILBO_PositionControl::_send_event(position_control_event_t event,
                                        uint16_t waypoint_idx) {
	position_control_event_data_t event_data;
	event_data.event = event;
	event_data.data = data;
	event_data.tick = tick_global;
	event_data.waypoint_index = waypoint_idx;
	event_data.command_id = 0;

	BILBO_Message_PositionControl_Event msg(event_data);
	sendMessage(msg);
}

// ============================================================================
// TURN TO HEADING
// ============================================================================

bilbo_position_control_output_t BILBO_PositionControl::_update_turn_to_heading(
		const bilbo_position_state_t& current_state) {

	bilbo_position_control_output_t output = {0.0f, 0.0f};

	float heading_error = _normalize_angle(
		_active_turn_command.heading_ref - current_state.psi);

	data.heading_error = heading_error;

	float max_rate = (_active_turn_command.max_angular_speed > 0.0f) ?
		_active_turn_command.max_angular_speed : config.max_turn_rate;

	// PI control
	float w_p = config.kp_angular * heading_error;
	float w_i = _angular_integral;
	float w_unsat = w_p + w_i;
	float w_sat = _clamp(w_unsat, -max_rate, max_rate);

	// Anti-windup
	bool is_saturated = fabsf(w_unsat - w_sat) > EPSILON;
	bool would_push_further = is_saturated && (
		(w_unsat > w_sat && heading_error > 0.0f) ||
		(w_unsat < w_sat && heading_error < 0.0f));

	if (!would_push_further) {
		_angular_integral += config.ki_angular * heading_error * config.Ts;
		float max_integral = max_rate / fmaxf(config.ki_angular, 0.01f);
		_angular_integral = _clamp(_angular_integral, -max_integral, max_integral);
	}

	output.psi_dot_cmd = w_sat;

	// Check completion
	float angle_tolerance = 0.05f;  // ~3 degrees
	if (fabsf(heading_error) < angle_tolerance) {
		_arrival_timer += config.Ts;
		if (_arrival_timer >= config.arrival_dwell_time) {
			_angular_integral = 0.0f;
			_arrival_timer = 0.0f;
			_set_mode(bilbo_position_control_mode_t::IDLE);
			_send_event(position_control_event_t::TURN_TO_HEADING_COMPLETED);
			return output;
		}
	} else {
		_arrival_timer = 0.0f;
	}

	// Check timeout
	if (_active_turn_command.timeout > 0.0f &&
		_elapsed_time > _active_turn_command.timeout) {
		_angular_integral = 0.0f;
		_arrival_timer = 0.0f;
		_set_mode(bilbo_position_control_mode_t::IDLE);
		_send_event(position_control_event_t::TURN_TO_HEADING_TIMEOUT);
	}

	return output;
}

// ============================================================================
// DRIVE TO POINT
// ============================================================================

bilbo_position_control_output_t BILBO_PositionControl::_update_drive_to_point(
		const bilbo_position_state_t& current_state,
		float current_v) {

	bilbo_position_control_output_t output = {0.0f, 0.0f};

	float dx = _active_move_command.x_target - current_state.x;
	float dy = _active_move_command.y_target - current_state.y;
	float dist = sqrtf(dx * dx + dy * dy);

	// -------------------------------------------------------------------------
	// Check completion
	// -------------------------------------------------------------------------

	if (dist < config.arrival_tolerance) {
		_arrival_timer += config.Ts;
		if (_arrival_timer >= config.arrival_dwell_time) {
			_angular_integral = 0.0f;
			_linear_integral = 0.0f;
			_arrival_timer = 0.0f;
			_reverse_mode_active = false;
			_set_mode(bilbo_position_control_mode_t::IDLE);
			_send_event(position_control_event_t::MOVE_TO_POINT_COMPLETED);
			return output;
		}
		// Inside tolerance, waiting for dwell
		data.speed_limit = 0.0f;
		data.remaining_path_length = dist;
		return output;
	}
	_arrival_timer = 0.0f;

	// -------------------------------------------------------------------------
	// Reverse mode with hysteresis
	// -------------------------------------------------------------------------

	float angle_to_target = atan2f(dy, dx);
	float heading_error_fwd = _normalize_angle(angle_to_target - current_state.psi);
	float abs_heading_error = fabsf(heading_error_fwd);

	if (!_reverse_mode_active && abs_heading_error > config.reverse_enter_angle) {
		_reverse_mode_active = true;
		_angular_integral = 0.0f;
	} else if (_reverse_mode_active && abs_heading_error < config.reverse_exit_angle) {
		_reverse_mode_active = false;
		_angular_integral = 0.0f;
	}

	// Carrot on line to target
	float lookahead = config.lookahead_base;
	float carrot_x = _active_move_command.x_target;
	float carrot_y = _active_move_command.y_target;

	if (dist > EPSILON && lookahead > EPSILON) {
		float step_back = fmaxf(0.0f, dist - lookahead);
		float inv_dist = 1.0f / (dist + EPSILON);
		carrot_x = _active_move_command.x_target - dx * inv_dist * step_back;
		carrot_y = _active_move_command.y_target - dy * inv_dist * step_back;
	}

	// Heading toward carrot
	float dx_carrot = carrot_x - current_state.x;
	float dy_carrot = carrot_y - current_state.y;
	float psi_carrot = atan2f(dy_carrot, dx_carrot);
	float carrot_dist = sqrtf(dx_carrot * dx_carrot + dy_carrot * dy_carrot);

	// In reverse mode, flip heading
	if (_reverse_mode_active) {
		psi_carrot = _normalize_angle(psi_carrot + M_PI);
	}

	float heading_error = _normalize_angle(psi_carrot - current_state.psi);
	data.heading_error = heading_error;

	// -------------------------------------------------------------------------
	// Velocity command
	// -------------------------------------------------------------------------

	float max_speed = (_active_move_command.max_speed > 0.0f) ?
		_active_move_command.max_speed : config.max_speed;

	// Velocity profile: sqrt deceleration curve when decel_limit set, else linear kp*d
	float v_p;
	if (config.decel_limit > 0.0f && carrot_dist > 0.0f) {
		v_p = sqrtf(2.0f * config.decel_limit * carrot_dist);
	} else {
		v_p = config.kp_linear * carrot_dist;
	}

	// Velocity damping: prevent overshoot by braking when already moving
	v_p = fmaxf(0.0f, v_p - config.kd_linear * fabsf(current_v));

	float v_i = _linear_integral;
	float v_unsat = v_p + v_i;
	float v_sat = _clamp(v_unsat, 0.0f, max_speed);

	if (fabsf(v_unsat - v_sat) < EPSILON) {
		_linear_integral += config.ki_linear * carrot_dist * config.Ts;
		_linear_integral = _clamp(_linear_integral, 0.0f, max_speed);
	}

	float cos_scale = fmaxf(0.0f, cosf(heading_error));
	float v_cmd = v_sat * cos_scale;

	if (_reverse_mode_active) {
		v_cmd = -v_cmd;
	}

	output.v_cmd = v_cmd;

	// -------------------------------------------------------------------------
	// Angular command
	// -------------------------------------------------------------------------

	float w_p = config.kp_angular * heading_error;
	float w_i = _angular_integral;
	float w_unsat = w_p + w_i;
	float w_sat = _clamp(w_unsat, -config.max_turn_rate, config.max_turn_rate);

	bool is_saturated = fabsf(w_unsat - w_sat) > EPSILON;
	bool would_push_further = is_saturated && (
		(w_unsat > w_sat && heading_error > 0.0f) ||
		(w_unsat < w_sat && heading_error < 0.0f));

	if (!would_push_further) {
		_angular_integral += config.ki_angular * heading_error * config.Ts;
		float max_integral = config.max_turn_rate / fmaxf(config.ki_angular, 0.01f);
		_angular_integral = _clamp(_angular_integral, -max_integral, max_integral);
	}

	// Fade near goal
	float fade_radius = 2.0f * config.arrival_tolerance;
	float w_fade = _clamp(dist / fade_radius, 0.0f, 1.0f);

	output.psi_dot_cmd = w_sat * w_fade;

	// -------------------------------------------------------------------------
	// Check timeout
	// -------------------------------------------------------------------------

	if (_active_move_command.timeout > 0.0f &&
		_elapsed_time > _active_move_command.timeout) {
		_angular_integral = 0.0f;
		_linear_integral = 0.0f;
		_arrival_timer = 0.0f;
		_reverse_mode_active = false;
		_set_mode(bilbo_position_control_mode_t::IDLE);
		_send_event(position_control_event_t::MOVE_TO_POINT_TIMEOUT);
	}

	// Update telemetry
	data.carrot_x = carrot_x;
	data.carrot_y = carrot_y;
	data.speed_limit = v_sat;
	data.remaining_path_length = dist;

	return output;
}

// ============================================================================
// UTILITY METHODS
// ============================================================================

float BILBO_PositionControl::_normalize_angle(float angle) {
	while (angle > M_PI) {
		angle -= 2.0f * M_PI;
	}
	while (angle < -M_PI) {
		angle += 2.0f * M_PI;
	}
	return angle;
}

float BILBO_PositionControl::_distance(float x1, float y1, float x2, float y2) {
	float dx = x2 - x1;
	float dy = y2 - y1;
	return sqrtf(dx * dx + dy * dy);
}

float BILBO_PositionControl::_clamp(float value, float lo, float hi) {
	if (value < lo) return lo;
	if (value > hi) return hi;
	return value;
}

float BILBO_PositionControl::_dot(float ax, float ay, float bx, float by) {
	return ax * bx + ay * by;
}
