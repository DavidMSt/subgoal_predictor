/*
 * bilbo_position_control.cpp
 *
 *  Created on: Jan 25, 2026
 *      Author: lehmann
 *
 *  DENSE PATH FOLLOWING IMPLEMENTATION
 *  ====================================
 *
 *  Key design principles:
 *
 *  1. DENSE PRE-PLANNED PATH
 *     - Path is a dense array of (x,y) points (~15mm uniform spacing)
 *     - Up to 1024 points with up to 16 explicit STOP indices
 *
 *  2. SPEED FROM PATH CURVATURE
 *     - Curvature estimated from upcoming path points (Menger curvature)
 *     - v_target = max_speed / (1 + curvature_gain * κ_max)
 *     - Low-pass filtered for smooth transitions
 *     - Deceleration near STOP points and path end
 *
 *  3. ADAPTIVE LOOKAHEAD (pure pursuit)
 *     - lookahead = v_target / kp_linear, clamped to lookahead_min
 *     - Carrot placed along path at lookahead distance ahead
 *     - At max_speed: lookahead = max_speed/kp_linear, so kp*carrot_dist ~ max_speed
 *
 *  4. REVERSE MODE (optional, per-path)
 *     - Robot drives backwards when target is behind
 *     - Hysteresis prevents oscillation
 */

#include "bilbo_position_control.h"
#include <cstring>
#include "twipr_communication.h"

#ifndef M_PI
#define M_PI 3.14159265358979323846f
#endif

static constexpr float EPSILON = 1e-6f;

// Number of segments ahead to search when projecting robot onto path
static constexpr uint16_t PROJECTION_SEARCH_WINDOW = 30;

// ============================================================================
// CONSTRUCTOR
// ============================================================================

BILBO_PositionControl::BILBO_PositionControl() {
	mode = bilbo_position_control_mode_t::IDLE;
	_path_state = bilbo_path_state_t::IDLE;
	_path_count = 0;
	_stop_count = 0;
	_progress = 0.0f;
	_reverse_mode_active = false;

	memset(_path_buffer, 0, sizeof(_path_buffer));
	memset(_cumul_dist, 0, sizeof(_cumul_dist));
	memset(_stop_indices, 0, sizeof(_stop_indices));
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
// PATH MANAGEMENT
// ============================================================================

void BILBO_PositionControl::clear_path() {
	_path_count = 0;
	_stop_count = 0;
	_path_state = bilbo_path_state_t::IDLE;
	_progress = 0.0f;
	_angular_integral = 0.0f;
	_linear_integral = 0.0f;
	_arrival_timer = 0.0f;
	_reverse_mode_active = false;
	_stop_reached_sent = false;
	_next_stop_ptr = 0;
	_path_max_speed = 0.0f;
	_path_max_spacing = 0.0f;
	_path_total_length = 0.0f;
	_v_target_smooth = 0.0f;
}

bool BILBO_PositionControl::add_path_point(float x, float y) {
	if (_path_count >= PATH_BUFFER_SIZE) {
		_send_event(position_control_event_t::PATH_BUFFER_FULL);
		return false;
	}

	_path_buffer[_path_count].x = x;
	_path_buffer[_path_count].y = y;
	_path_count++;
	return true;
}

bool BILBO_PositionControl::add_path_points_batch(const path_points_batch_t& batch) {
	if (batch.count == 0 || batch.count > BILBO_POSITION_CONTROL_BATCH_SIZE) {
		return false;
	}
	if (batch.start_index + batch.count > PATH_BUFFER_SIZE) {
		_send_event(position_control_event_t::PATH_BUFFER_FULL);
		return false;
	}

	memcpy(&_path_buffer[batch.start_index], batch.points,
			batch.count * sizeof(path_point_t));

	uint16_t end = batch.start_index + batch.count;
	if (end > _path_count) {
		_path_count = end;
	}
	return true;
}

bool BILBO_PositionControl::set_path(const path_point_t* pts, uint16_t count) {
	if (count > PATH_BUFFER_SIZE) {
		_send_event(position_control_event_t::PATH_BUFFER_FULL);
		return false;
	}

	memcpy(_path_buffer, pts, count * sizeof(path_point_t));
	_path_count = count;
	return true;
}

bool BILBO_PositionControl::add_stop_index(uint16_t index) {
	if (_stop_count >= MAX_STOPS) {
		return false;
	}
	_stop_indices[_stop_count] = index;
	_stop_count++;
	return true;
}

uint16_t BILBO_PositionControl::get_path_point_count() const {
	return _path_count;
}

void BILBO_PositionControl::spiPathReceived(const path_point_t *spi_buffer, uint16_t count) {
	clear_path();
	if (count > PATH_BUFFER_SIZE) {
		count = PATH_BUFFER_SIZE;
	}
	set_path(spi_buffer, count);
	send_info("SPI path received: %d points", count);
}

// ============================================================================
// PATH FOLLOWING - EXECUTION CONTROL
// ============================================================================

bool BILBO_PositionControl::start_path(const bilbo_path_start_cmd_t& command) {
	if (_path_count < 2) {
		return false;
	}

	if (mode != bilbo_position_control_mode_t::IDLE) {
		return false;
	}

	// Compute cumulative distances
	_compute_cumulative_distances();

	// Resolve max speed
	_path_max_speed = (command.max_speed > 0.0f) ? command.max_speed : config.max_speed;

	// Resolve max spacing: auto-detect from path if not specified
	if (command.max_spacing > 0.0f) {
		_path_max_spacing = command.max_spacing;
	} else {
		// Find the maximum inter-point distance
		_path_max_spacing = 0.0f;
		for (uint16_t i = 1; i < _path_count; i++) {
			float seg_len = _cumul_dist[i] - _cumul_dist[i - 1];
			if (seg_len > _path_max_spacing) {
				_path_max_spacing = seg_len;
			}
		}
		if (_path_max_spacing < EPSILON) {
			_path_max_spacing = 0.01f;  // Fallback: 10mm
		}
	}

	_path_total_length = _cumul_dist[_path_count - 1];

	// Initialize state
	_progress = 0.0f;
	_angular_integral = 0.0f;
	_linear_integral = 0.0f;
	_arrival_timer = 0.0f;
	_elapsed_time = 0.0f;
	_reverse_mode_active = false;
	_stop_reached_sent = false;
	_next_stop_ptr = 0;

	// Initialize carrot at first path point
	_carrot_x = _path_buffer[0].x;
	_carrot_y = _path_buffer[0].y;

	// Store command
	_active_path_command = command;

	// Set mode and state
	_path_state = bilbo_path_state_t::RUNNING;
	_set_mode(bilbo_position_control_mode_t::FOLLOW_PATH);

	send_info("PATH START: %d pts, %d stops, max_speed=%.2f, max_spacing=%.3f, total_len=%.2f",
	          _path_count, _stop_count, _path_max_speed, _path_max_spacing, _path_total_length);
	for (uint8_t i = 0; i < _stop_count; i++) {
		send_info("  STOP[%d] = index %d (%.2f, %.2f)", i, _stop_indices[i],
		          _path_buffer[_stop_indices[i]].x, _path_buffer[_stop_indices[i]].y);
	}

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
	this->clear_path();
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
	data.buffer_capacity = PATH_BUFFER_SIZE;
	data.buffer_used = _path_count;
	data.output = output;
	data.elapsed_time = _elapsed_time;

	return output;
}

// ============================================================================
// PATH GEOMETRY
// ============================================================================

void BILBO_PositionControl::_compute_cumulative_distances() {
	_cumul_dist[0] = 0.0f;
	for (uint16_t i = 1; i < _path_count; i++) {
		float dx = _path_buffer[i].x - _path_buffer[i - 1].x;
		float dy = _path_buffer[i].y - _path_buffer[i - 1].y;
		_cumul_dist[i] = _cumul_dist[i - 1] + sqrtf(dx * dx + dy * dy);
	}
}

// ============================================================================
// CURVATURE ESTIMATION
// ============================================================================

/**
 * Estimate the maximum path curvature in a lookahead window ahead of the
 * given progress position.
 *
 * Uses the Menger curvature formula on triplets of path points:
 *   κ = 2|cross(B-A, C-A)| / (|B-A| * |C-B| * |C-A|)
 *
 * A stride of ~50mm (in point indices) is used for noise rejection.
 * The maximum curvature over the window is returned so the robot slows
 * down before entering the tightest part of an upcoming curve.
 *
 * Returns 0.0 if the path is too short for curvature estimation.
 */
float BILBO_PositionControl::_estimate_curvature_ahead(
		float at_progress, float lookahead_dist) const {

	if (_path_count < 3) return 0.0f;

	uint16_t start_idx = (uint16_t)at_progress;
	if (start_idx >= _path_count - 1) start_idx = _path_count - 2;

	// Find end index based on lookahead distance
	float start_arc = _cumul_dist[start_idx];
	float end_arc = start_arc + lookahead_dist;

	uint16_t end_idx = start_idx;
	while (end_idx < _path_count - 1 && _cumul_dist[end_idx] < end_arc) {
		end_idx++;
	}

	// Compute stride: ~50mm chord for robust curvature estimation
	// Adapts to actual path spacing
	float avg_spacing = (_path_count > 1)
		? (_path_total_length / (float)(_path_count - 1))
		: 0.015f;
	uint16_t stride = (uint16_t)(0.05f / fmaxf(avg_spacing, 0.001f));
	if (stride < 1) stride = 1;
	if (stride > 15) stride = 15;

	// Need at least 2*stride points for a single curvature measurement
	if (end_idx < start_idx + 2 * stride) {
		// Not enough lookahead — use a single measurement at current position
		if (start_idx + 2 * stride < _path_count) {
			end_idx = start_idx + 2 * stride;
		} else {
			return 0.0f;
		}
	}

	float max_kappa = 0.0f;

	for (uint16_t i = start_idx; i + 2 * stride <= end_idx && i + 2 * stride < _path_count; i++) {
		float ax = _path_buffer[i].x;
		float ay = _path_buffer[i].y;
		float bx = _path_buffer[i + stride].x;
		float by = _path_buffer[i + stride].y;
		float cx = _path_buffer[i + 2 * stride].x;
		float cy = _path_buffer[i + 2 * stride].y;

		// Vectors AB and AC
		float abx = bx - ax, aby = by - ay;
		float bcx = cx - bx, bcy = cy - by;
		float acx = cx - ax, acy = cy - ay;

		// Menger curvature: κ = 2|cross(AB, AC)| / (|AB| * |BC| * |AC|)
		float cross_mag = fabsf(abx * acy - aby * acx);
		float ab_len = sqrtf(abx * abx + aby * aby);
		float bc_len = sqrtf(bcx * bcx + bcy * bcy);
		float ac_len = sqrtf(acx * acx + acy * acy);

		float denom = ab_len * bc_len * ac_len;
		if (denom > 1e-10f) {
			float kappa = 2.0f * cross_mag / denom;
			if (kappa > max_kappa) max_kappa = kappa;
		}
	}

	return max_kappa;
}

// ============================================================================
// PATH TRACKING HELPERS
// ============================================================================

/**
 * Project robot position onto path segments starting from last_progress.
 * Searches forward up to PROJECTION_SEARCH_WINDOW segments.
 * Returns the floating-point index of the closest projection (monotonic: >= last_progress).
 */
float BILBO_PositionControl::_project_onto_path(float robot_x, float robot_y,
                                                 float last_progress) const {
	uint16_t start_seg = (uint16_t)last_progress;
	if (start_seg >= _path_count - 1) {
		start_seg = _path_count - 2;
	}

	uint16_t end_seg = start_seg + PROJECTION_SEARCH_WINDOW;
	if (end_seg >= _path_count - 1) {
		end_seg = _path_count - 2;
	}

	float best_progress = last_progress;
	float best_dist_sq = 1e30f;

	for (uint16_t i = start_seg; i <= end_seg; i++) {
		float ax = _path_buffer[i].x;
		float ay = _path_buffer[i].y;
		float bx = _path_buffer[i + 1].x;
		float by = _path_buffer[i + 1].y;

		float dx = bx - ax;
		float dy = by - ay;
		float len_sq = dx * dx + dy * dy;

		float t;
		if (len_sq < EPSILON) {
			t = 0.0f;
		} else {
			t = ((robot_x - ax) * dx + (robot_y - ay) * dy) / len_sq;
			t = _clamp(t, 0.0f, 1.0f);
		}

		float proj_x = ax + t * dx;
		float proj_y = ay + t * dy;
		float dist_sq = (robot_x - proj_x) * (robot_x - proj_x) +
		                (robot_y - proj_y) * (robot_y - proj_y);

		float candidate = (float)i + t;

		// Only accept if monotonically forward
		if (candidate >= last_progress && dist_sq < best_dist_sq) {
			best_dist_sq = dist_sq;
			best_progress = candidate;
		}
	}

	return best_progress;
}

/**
 * Advance along path from a given progress by a distance in meters.
 * Returns new progress value, clamped to [0, path_count-1].
 */
float BILBO_PositionControl::_advance_along_path(float from_progress,
                                                  float distance_meters) const {
	if (_path_count < 2) return from_progress;

	float current_arc = _cumul_dist_at(from_progress);
	float target_arc = current_arc + distance_meters;

	// Clamp to path end
	if (target_arc >= _cumul_dist[_path_count - 1]) {
		return (float)(_path_count - 1);
	}
	if (target_arc <= 0.0f) {
		return 0.0f;
	}

	// Binary search for the segment containing target_arc
	uint16_t lo = 0, hi = _path_count - 1;
	while (lo < hi - 1) {
		uint16_t mid = (lo + hi) / 2;
		if (_cumul_dist[mid] <= target_arc) {
			lo = mid;
		} else {
			hi = mid;
		}
	}

	// Interpolate within segment [lo, lo+1]
	float seg_start = _cumul_dist[lo];
	float seg_end = _cumul_dist[lo + 1];
	float seg_len = seg_end - seg_start;

	float t = 0.0f;
	if (seg_len > EPSILON) {
		t = (target_arc - seg_start) / seg_len;
		t = _clamp(t, 0.0f, 1.0f);
	}

	return (float)lo + t;
}

/**
 * Interpolate path position at a floating-point progress value.
 */
void BILBO_PositionControl::_interpolate_path(float progress,
                                               float& out_x, float& out_y) const {
	if (_path_count == 0) {
		out_x = 0.0f;
		out_y = 0.0f;
		return;
	}

	// Clamp progress
	if (progress <= 0.0f) {
		out_x = _path_buffer[0].x;
		out_y = _path_buffer[0].y;
		return;
	}
	if (progress >= (float)(_path_count - 1)) {
		out_x = _path_buffer[_path_count - 1].x;
		out_y = _path_buffer[_path_count - 1].y;
		return;
	}

	uint16_t idx = (uint16_t)progress;
	float t = progress - (float)idx;

	out_x = _path_buffer[idx].x + t * (_path_buffer[idx + 1].x - _path_buffer[idx].x);
	out_y = _path_buffer[idx].y + t * (_path_buffer[idx + 1].y - _path_buffer[idx].y);
}

/**
 * Get cumulative arc length at a floating-point progress value.
 */
float BILBO_PositionControl::_cumul_dist_at(float progress) const {
	if (_path_count < 2) return 0.0f;

	if (progress <= 0.0f) return _cumul_dist[0];
	if (progress >= (float)(_path_count - 1)) return _cumul_dist[_path_count - 1];

	uint16_t idx = (uint16_t)progress;
	float t = progress - (float)idx;

	return _cumul_dist[idx] + t * (_cumul_dist[idx + 1] - _cumul_dist[idx]);
}

// ============================================================================
// PATH FOLLOWING UPDATE
// ============================================================================

bilbo_position_control_output_t BILBO_PositionControl::_update_follow_path(
		const bilbo_position_state_t& current_state,
		float current_v) {

	bilbo_position_control_output_t output = {0.0f, 0.0f};

	if (_path_state != bilbo_path_state_t::RUNNING || _path_count < 2) {
		return output;
	}

	// -----------------------------------------------------------------
	// 1. TIMEOUT check
	// -----------------------------------------------------------------
	if (_active_path_command.timeout > 0.0f &&
		_elapsed_time > _active_path_command.timeout) {
		_on_path_timeout();
		_path_state = bilbo_path_state_t::IDLE;
		_set_mode(bilbo_position_control_mode_t::IDLE);
		return output;
	}

	// -----------------------------------------------------------------
	// 2. PROJECT robot onto path (monotonic forward)
	// -----------------------------------------------------------------
	_progress = _project_onto_path(current_state.x, current_state.y, _progress);

	// -----------------------------------------------------------------
	// 3-4. TARGET SPEED from path curvature
	//      Estimate curvature from upcoming path points using Menger
	//      curvature formula, then map to speed:
	//        v = max_speed / (1 + curvature_gain * κ_max)
	//      Low-pass filter the result for smooth transitions.
	// -----------------------------------------------------------------
	float kappa = _estimate_curvature_ahead(_progress, config.curvature_lookahead);
	float v_target_raw = _path_max_speed / (1.0f + config.curvature_gain * kappa);
	v_target_raw = _clamp(v_target_raw, 0.0f, _path_max_speed);

	// Exponential smoothing (time constant ~100ms for gentle transitions)
	static constexpr float SPEED_SMOOTH_TAU = 0.1f;  // [s]
	float alpha_smooth = config.Ts / (config.Ts + SPEED_SMOOTH_TAU);
	_v_target_smooth = alpha_smooth * v_target_raw + (1.0f - alpha_smooth) * _v_target_smooth;
	float v_target = _v_target_smooth;

	// -----------------------------------------------------------------
	// 5. STOP DECELERATION
	// -----------------------------------------------------------------
	float robot_arc = _cumul_dist_at(_progress);

	// Decelerate toward next STOP point
	if (_next_stop_ptr < _stop_count) {
		uint16_t stop_idx = _stop_indices[_next_stop_ptr];
		float d_to_stop = _cumul_dist[stop_idx] - robot_arc;
		if (d_to_stop > 0.0f) {
			float v_brake;
			if (config.decel_limit > 0.0f) {
				v_brake = sqrtf(2.0f * config.decel_limit * d_to_stop);
			} else {
				v_brake = config.kp_linear * d_to_stop;
			}
			v_target = fminf(v_target, v_brake);
		}
	}

	// Always decelerate toward path end (last point)
	float d_to_end = _cumul_dist[_path_count - 1] - robot_arc;
	if (d_to_end > 0.0f) {
		float v_brake_end;
		if (config.decel_limit > 0.0f) {
			v_brake_end = sqrtf(2.0f * config.decel_limit * d_to_end);
		} else {
			v_brake_end = config.kp_linear * d_to_end;
		}
		v_target = fminf(v_target, v_brake_end);
	} else {
		v_target = 0.0f;
	}

	// -----------------------------------------------------------------
	// 6. COMPUTE LOOKAHEAD
	// -----------------------------------------------------------------
	float lookahead;
	if (config.kp_linear > EPSILON) {
		// Scale lookahead with target speed: faster = look further ahead
		lookahead = v_target / config.kp_linear;
	} else {
		// No kp_linear: use lookahead_base scaled by speed fraction
		lookahead = config.lookahead_base * (v_target / fmaxf(_path_max_speed, EPSILON));
	}
	lookahead = fmaxf(lookahead, config.lookahead_min);

	// -----------------------------------------------------------------
	// 7. PLACE CARROT along path
	// -----------------------------------------------------------------
	float carrot_progress = _advance_along_path(_progress, lookahead);

	// Clamp carrot at next STOP index
	if (_next_stop_ptr < _stop_count) {
		uint16_t stop_idx = _stop_indices[_next_stop_ptr];
		if (carrot_progress > (float)stop_idx) {
			carrot_progress = (float)stop_idx;
		}
	}

	// Clamp at path end
	if (carrot_progress > (float)(_path_count - 1)) {
		carrot_progress = (float)(_path_count - 1);
	}

	_interpolate_path(carrot_progress, _carrot_x, _carrot_y);

	// Distance and angle to carrot
	float dx_carrot = _carrot_x - current_state.x;
	float dy_carrot = _carrot_y - current_state.y;
	float carrot_dist = sqrtf(dx_carrot * dx_carrot + dy_carrot * dy_carrot);
	float angle_to_carrot = atan2f(dy_carrot, dx_carrot);

	// Heading error (forward)
	float heading_error_fwd = _normalize_angle(angle_to_carrot - current_state.psi);

	// -----------------------------------------------------------------
	// 8. REVERSE MODE (if allow_reverse)
	// -----------------------------------------------------------------
	float heading_error = heading_error_fwd;

	if (_active_path_command.allow_reverse) {
		float abs_heading_error = fabsf(heading_error_fwd);

		if (!_reverse_mode_active && abs_heading_error > config.reverse_enter_angle) {
			_reverse_mode_active = true;
			_angular_integral = 0.0f;
		} else if (_reverse_mode_active && abs_heading_error < config.reverse_exit_angle) {
			_reverse_mode_active = false;
			_angular_integral = 0.0f;
		}

		if (_reverse_mode_active) {
			heading_error = _normalize_angle(heading_error_fwd + M_PI);
		}
	}

	data.heading_error = heading_error;
	data.carrot_distance = carrot_dist;

	// -----------------------------------------------------------------
	// 9. SPEED COMMAND
	// -----------------------------------------------------------------
	float v_cmd;
	if (config.decel_limit > EPSILON) {
		// Deceleration profile already limits v_target, use it directly
		// Pre-compensate for velocity damping so steady-state speed matches v_target:
		// at equilibrium: v = v_cmd - kd*v  →  v = v_cmd/(1+kd)
		// so set v_cmd = v_target * (1+kd) to get v ≈ v_target after damping
		v_cmd = v_target * (1.0f + config.kd_linear);
	} else {
		// Proportional fallback: speed = min(v_target, kp * distance_to_carrot)
		v_cmd = fminf(v_target, config.kp_linear * carrot_dist);
	}

	// Velocity damping
	v_cmd = fmaxf(0.0f, v_cmd - config.kd_linear * fabsf(current_v));

	// Scale by cos(heading_error) - slow down when not facing carrot
	float cos_scale = fmaxf(0.0f, cosf(heading_error));
	v_cmd *= cos_scale;

	// Reverse mode: negate velocity
	if (_reverse_mode_active) {
		v_cmd = -v_cmd;
	}

	output.v_cmd = v_cmd;
	data.speed_limit = v_target;

	// -----------------------------------------------------------------
	// 10. ANGULAR COMMAND - PI control with anti-windup
	// -----------------------------------------------------------------
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

	// Fade yaw rate near carrot to prevent jitter at stops/end
	float fade_radius = 2.0f * config.arrival_tolerance;
	float w_fade = _clamp(carrot_dist / fade_radius, 0.0f, 1.0f);

	output.psi_dot_cmd = w_sat * w_fade;

	// -----------------------------------------------------------------
	// 11. ARRIVAL CHECKS
	// -----------------------------------------------------------------

	// Get robot's position on path
	float robot_path_x, robot_path_y;
	_interpolate_path(_progress, robot_path_x, robot_path_y);
	float dist_to_robot_proj = _distance(current_state.x, current_state.y,
	                                      robot_path_x, robot_path_y);

	// PATH END check
	float last_pt_dist = _distance(current_state.x, current_state.y,
	                                _path_buffer[_path_count - 1].x,
	                                _path_buffer[_path_count - 1].y);
	float progress_threshold = (float)(_path_count - 1) - 1.0f;
	bool near_end = (_progress >= progress_threshold) &&
	                (last_pt_dist < config.arrival_tolerance);

	// Debug: log when near path end (throttled to ~2 Hz via tick counter)
	if (_progress >= progress_threshold - 5.0f) {
		static uint16_t _dbg_tick = 0;
		if (++_dbg_tick >= 50) {  // every 50 ticks = 0.5s at 100Hz
			send_info("PATH END: prog=%.1f/%d, dist=%.3f, tol=%.3f, near=%d, v_tgt=%.2f, v_cmd=%.2f",
			          _progress, _path_count - 1, last_pt_dist,
			          config.arrival_tolerance, (int)near_end, v_target, output.v_cmd);
			_dbg_tick = 0;
		}
	}

	// STOP check (only if not at end)
	bool near_stop = false;
	uint16_t current_stop_idx = 0;
	if (_next_stop_ptr < _stop_count) {
		current_stop_idx = _stop_indices[_next_stop_ptr];
		float stop_pt_dist = _distance(current_state.x, current_state.y,
		                                _path_buffer[current_stop_idx].x,
		                                _path_buffer[current_stop_idx].y);
		near_stop = (_progress >= (float)current_stop_idx - 1.0f) &&
		            (stop_pt_dist < config.arrival_tolerance);
	}

	if (near_end) {
		// PATH END arrival — output zero while dwelling
		output.v_cmd = 0.0f;
		output.psi_dot_cmd = 0.0f;
		_arrival_timer += config.Ts;
		if (_arrival_timer >= config.arrival_dwell_time) {
			send_info("PATH FINISHED: progress=%.1f, last_pt_dist=%.3f", _progress, last_pt_dist);
			_on_path_finished();
			_path_state = bilbo_path_state_t::IDLE;
			_set_mode(bilbo_position_control_mode_t::IDLE);
		}
		return output;
	} else if (near_stop) {
		// STOP point arrival — output zero while dwelling
		if (!_stop_reached_sent) {
			send_info("STOP REACHED: stop[%d] idx=%d, progress=%.1f, dist=%.3f",
			          _next_stop_ptr, current_stop_idx,
			          _progress, _distance(current_state.x, current_state.y,
			                               _path_buffer[current_stop_idx].x,
			                               _path_buffer[current_stop_idx].y));
			_on_stop_reached(current_stop_idx);
			_stop_reached_sent = true;
		}

		output.v_cmd = 0.0f;
		output.psi_dot_cmd = 0.0f;
		_arrival_timer += config.Ts;
		if (_arrival_timer >= config.stop_dwell_time) {
			send_info("STOP COMPLETED: stop[%d] idx=%d, dwell=%.2fs",
			          _next_stop_ptr, current_stop_idx, config.stop_dwell_time);
			_on_stop_completed(current_stop_idx);
			_next_stop_ptr++;
			_arrival_timer = 0.0f;
			_angular_integral = 0.0f;
			_stop_reached_sent = false;
		}
		return output;
	} else {
		_arrival_timer = 0.0f;
		_stop_reached_sent = false;
	}

	// -----------------------------------------------------------------
	// 12. FINAL APPROACH — when near path end or STOP waypoint but
	//     outside tolerance, override with move_to_point-like drive.
	//     Allows reverse to recover from overshoot without oscillation.
	// -----------------------------------------------------------------

	// 12a. Path endpoint — activate within stopping distance
	float stopping_dist_end = (config.decel_limit > EPSILON)
		? (_path_max_speed * _path_max_speed) / (2.0f * config.decel_limit)
		: 0.5f;
	bool approaching_end = (d_to_end < stopping_dist_end) || (d_to_end < 0.0f);

	if (approaching_end && !near_end) {
		float dx_last = _path_buffer[_path_count - 1].x - current_state.x;
		float dy_last = _path_buffer[_path_count - 1].y - current_state.y;
		float dist_last = sqrtf(dx_last * dx_last + dy_last * dy_last);
		float angle_to_last = atan2f(dy_last, dx_last);
		float he_last = _normalize_angle(angle_to_last - current_state.psi);

		// Speed: sqrt decel toward last point (same as move_to_point)
		float v_final;
		if (config.decel_limit > EPSILON) {
			v_final = sqrtf(2.0f * config.decel_limit * dist_last);
		} else {
			v_final = config.kp_linear * dist_last;
		}
		v_final = fmaxf(0.0f, v_final - config.kd_linear * fabsf(current_v));
		v_final = fminf(v_final, _path_max_speed);

		// Allow reverse if overshot (heading > 120°)
		bool reverse_last = fabsf(he_last) > config.reverse_enter_angle;
		if (reverse_last) {
			he_last = _normalize_angle(he_last + M_PI);
			output.v_cmd = -v_final * fmaxf(0.0f, cosf(he_last));
		} else {
			output.v_cmd = v_final * fmaxf(0.0f, cosf(he_last));
		}

		// Angular with fade near target (prevent jitter)
		float w_last = _clamp(config.kp_angular * he_last,
		                       -config.max_turn_rate, config.max_turn_rate);
		float fade_last = _clamp(dist_last / (2.0f * config.arrival_tolerance), 0.0f, 1.0f);
		output.psi_dot_cmd = w_last * fade_last;
	}

	// 12b. STOP waypoint approach — move_to_point-like drive toward stop.
	//      Activates within stopping distance (v_max²/(2*a)) so the sqrt
	//      decel profile has full room to brake smoothly.  Allows reverse
	//      to recover from overshoot without oscillation.
	if (_next_stop_ptr < _stop_count && !near_stop) {
		uint16_t stop_idx = _stop_indices[_next_stop_ptr];
		float stop_x = _path_buffer[stop_idx].x;
		float stop_y = _path_buffer[stop_idx].y;
		float dx_stop = stop_x - current_state.x;
		float dy_stop = stop_y - current_state.y;
		float dist_stop = sqrtf(dx_stop * dx_stop + dy_stop * dy_stop);

		// Stopping distance from max speed: d = v²/(2a)
		float stopping_dist = (config.decel_limit > EPSILON)
			? (_path_max_speed * _path_max_speed) / (2.0f * config.decel_limit)
			: 0.5f;  // fallback 50cm

		// Activate when arc-length to stop < stopping distance, or past the stop
		float arc_to_stop = _cumul_dist[stop_idx] - robot_arc;
		bool approaching_stop = (arc_to_stop < stopping_dist) || (arc_to_stop < 0.0f);

		if (approaching_stop) {
			float angle_to_stop = atan2f(dy_stop, dx_stop);
			float he_stop = _normalize_angle(angle_to_stop - current_state.psi);

			// Speed: sqrt decel toward stop point (based on Euclidean distance)
			float v_stop;
			if (config.decel_limit > EPSILON) {
				v_stop = sqrtf(2.0f * config.decel_limit * dist_stop);
			} else {
				v_stop = config.kp_linear * dist_stop;
			}
			v_stop = fmaxf(0.0f, v_stop - config.kd_linear * fabsf(current_v));
			v_stop = fminf(v_stop, _path_max_speed);

			// Allow reverse if overshot
			bool reverse_stop = fabsf(he_stop) > config.reverse_enter_angle;
			if (reverse_stop) {
				he_stop = _normalize_angle(he_stop + M_PI);
				output.v_cmd = -v_stop * fmaxf(0.0f, cosf(he_stop));
			} else {
				output.v_cmd = v_stop * fmaxf(0.0f, cosf(he_stop));
			}

			// Angular with fade near target
			float w_stop = _clamp(config.kp_angular * he_stop,
			                       -config.max_turn_rate, config.max_turn_rate);
			float fade_stop = _clamp(dist_stop / (2.0f * config.arrival_tolerance), 0.0f, 1.0f);
			output.psi_dot_cmd = w_stop * fade_stop;
		}
	}

	// Update telemetry
	data.path_point_count = _path_count;
	data.current_index = (uint16_t)_progress;
	data.carrot_x = _carrot_x;
	data.carrot_y = _carrot_y;
	data.remaining_path_length = fmaxf(0.0f, d_to_end);
	data.progress = _progress;

	return output;
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

void BILBO_PositionControl::_on_stop_reached(uint16_t path_idx) {
	_send_event(position_control_event_t::WAYPOINT_REACHED, path_idx);
	callbacks.stop_reached.call(path_idx);
}

void BILBO_PositionControl::_on_stop_completed(uint16_t path_idx) {
	_send_event(position_control_event_t::WAYPOINT_COMPLETED, path_idx);
	callbacks.stop_completed.call(path_idx);
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

	// Velocity profile: use actual distance to target for speed (not carrot_dist)
	// sqrt profile gives large values at far distances that survive kd damping
	// and are only clamped to max_speed at the final v_sat step
	float v_p;
	if (config.decel_limit > 0.0f && dist > 0.0f) {
		v_p = sqrtf(2.0f * config.decel_limit * dist);
	} else {
		v_p = config.kp_linear * dist;
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
