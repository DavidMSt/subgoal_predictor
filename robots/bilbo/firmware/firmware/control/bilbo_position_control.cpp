/*
 * bilbo_position_control.cpp
 *
 *  Created on: Jan 9, 2026
 *      Author: lehmann
 *
 *  Improvements (Jan 2026):
 *   - POSITION_TO_POINT completion now uses distance-only (like Python MoveToTarget)
 *     to avoid ill-conditioned angle-to-target near goal.
 *   - cos(e_psi) speed scaling is clamped to >= 0 to avoid unintentional reversal
 *     due to heading noise / overshoot near the target.
 *   - Angular command is scaled down near the goal (distance-based fade) to reduce
 *     “spin jitter” when close to the target.
 */

#include "bilbo_position_control.h"

#include <algorithm>
#include <cmath>

// Provided by your system (global tick counter)
extern uint32_t tick_global;

// ----- helpers -----
static inline float clampf(float v, float lo, float hi) {
	return std::max(lo, std::min(v, hi));
}

static inline float wrapToPi(float a) {
	// Wrap to [-pi, pi]
	constexpr float PI = 3.14159265358979323846f;
	while (a > PI)
		a -= 2.0f * PI;
	while (a < -PI)
		a += 2.0f * PI;
	return a;
}

static inline float hypotf_safe(float x, float y) {
	return std::sqrt(x * x + y * y);
}

BILBO_PositionControl::BILBO_PositionControl() {
	// NOTE: config is expected to be set via set_config().
	// We still initialize safe internal state.

	this->current_mode = bilbo_position_control_mode_t::NONE;

	this->_position_integral_error = 0.0f;
	this->_angle_integral_error = 0.0f;

	this->_arrival_hold_time = 0.0f;
	this->_was_inside_arrival_region = false;

	this->_current_element_id = 0;
	this->_element_start_tick = 0;

	// Telemetry init (no defaults in struct -> assign explicitly)
	this->_data.current_mode = bilbo_position_control_mode_t::NONE;
	this->_data.is_executing_command = false;
	this->_data.current_output.v_cmd = 0.0f;
	this->_data.current_output.psi_dot_cmd = 0.0f;
}

bilbo_position_control_output_t BILBO_PositionControl::update(
		bilbo_position_state_t current_state) {

	bilbo_position_control_output_t out;
	out.v_cmd = 0.0f;
	out.psi_dot_cmd = 0.0f;

	// This flag reflects whether we are inside the completion region this tick
	// (the per-mode controllers update _was_inside_arrival_region and _arrival_hold_time).
	bool inside_arrival_region = false;

	// ----- compute control output for current mode -----
	switch (this->current_mode) {
	case bilbo_position_control_mode_t::NONE: {
		// Idle: keep things quiet
		this->_position_integral_error = 0.0f;
		this->_angle_integral_error = 0.0f;
		this->_arrival_hold_time = 0.0f;
		this->_was_inside_arrival_region = false;

		out.v_cmd = 0.0f;
		out.psi_dot_cmd = 0.0f;
		break;
	}

	case bilbo_position_control_mode_t::POSITION_TO_POINT: {
		const float max_v =
				(this->_current_position_command.max_speed > 0.0f) ?
						this->_current_position_command.max_speed :
						this->config.max_speed_forward;

		out = this->_position_control_to_point(current_state,
				this->_current_position_command.position_ref.x_target,
				this->_current_position_command.position_ref.y_target, max_v);

		inside_arrival_region = this->_was_inside_arrival_region;
		break;
	}

	case bilbo_position_control_mode_t::TURN_TO_HEADING: {
		const float max_w =
				(this->_current_heading_command.max_angular_speed > 0.0f) ?
						this->_current_heading_command.max_angular_speed :
						this->config.max_speed_turn;

		out = this->_turn_to_heading(current_state,
				this->_current_heading_command.heading_ref.psi_target, max_w);

		inside_arrival_region = this->_was_inside_arrival_region;
		break;
	}

	default: {
		// Unknown -> safe stop
		out.v_cmd = 0.0f;
		out.psi_dot_cmd = 0.0f;
		this->current_mode = bilbo_position_control_mode_t::NONE;
		break;
	}
	}

	// ----- timeout handling -----
	// If a timeout is configured (>0), abort when elapsed >= timeout.
	if (this->is_executing_command()) {
		float timeout_s = 0.0f;

		if (this->current_mode
				== bilbo_position_control_mode_t::POSITION_TO_POINT) {
			timeout_s = this->_current_position_command.timeout;
		} else if (this->current_mode
				== bilbo_position_control_mode_t::TURN_TO_HEADING) {
			timeout_s = this->_current_heading_command.timeout;
		}

		if (timeout_s > 0.0f) {
			// elapsed time = (tick_global - start_tick) * Ts
			const uint32_t elapsed_ticks = static_cast<uint32_t>(tick_global
					- this->_element_start_tick);
			const float elapsed_s = static_cast<float>(elapsed_ticks)
					* this->config.Ts;

			if (elapsed_s >= timeout_s) {
				this->_on_timeout();

				// Immediately output stop
				out.v_cmd = 0.0f;
				out.psi_dot_cmd = 0.0f;

				// Update telemetry and return
				this->_data.current_mode = this->current_mode;
				this->_data.current_output = out;
				this->_data.is_executing_command = this->is_executing_command();
				return out;
			}
		}
	}

	// ----- completion handling (arrival-hold) -----
	if (this->is_executing_command()) {
		if (inside_arrival_region
				&& this->_arrival_hold_time >= this->config.arrival_time) {
			this->_on_command_finished();

			// Stop output at completion moment
			out.v_cmd = 0.0f;
			out.psi_dot_cmd = 0.0f;
		}
	}

	// ----- telemetry -----
	this->_data.current_mode = this->current_mode;
	this->_data.current_position_command = this->_current_position_command;
	this->_data.current_heading_command = this->_current_heading_command;
	this->_data.current_output = out;
	this->_data.is_executing_command = this->is_executing_command();

	return out;
}

void BILBO_PositionControl::set_config(bilbo_position_control_config_t config) {
	this->config = config;
	this->reset();
}

void BILBO_PositionControl::reset() {
	this->abort_current_command();

	this->_position_integral_error = 0.0f;
	this->_angle_integral_error = 0.0f;

	this->_arrival_hold_time = 0.0f;
	this->_was_inside_arrival_region = false;

	this->_current_element_id = 0;
	this->_element_start_tick = static_cast<uint32_t>(tick_global);

	this->_data.current_mode = bilbo_position_control_mode_t::NONE;
	this->_data.is_executing_command = false;
	this->_data.current_output.v_cmd = 0.0f;
	this->_data.current_output.psi_dot_cmd = 0.0f;
}

bilbo_position_control_config_t BILBO_PositionControl::get_config() {
	return this->config;
}

bool BILBO_PositionControl::set_position_command(position_command_t command) {
	if (this->is_executing_command()) {
		return false;
	}

	this->reset();

	this->_current_position_command = command;
	this->_current_element_id = command.id;
	this->_element_start_tick = static_cast<uint32_t>(tick_global);

	this->current_mode = bilbo_position_control_mode_t::POSITION_TO_POINT;
	return true;
}

bool BILBO_PositionControl::set_heading_command(heading_command_t command) {
	if (this->is_executing_command()) {
		return false;
	}

	this->reset();

	this->_current_heading_command = command;
	this->_current_element_id = command.id;
	this->_element_start_tick = static_cast<uint32_t>(tick_global);

	this->current_mode = bilbo_position_control_mode_t::TURN_TO_HEADING;
	return true;
}

void BILBO_PositionControl::abort_current_command() {
	this->current_mode = bilbo_position_control_mode_t::NONE;
}

bool BILBO_PositionControl::is_executing_command() {
	return this->current_mode != bilbo_position_control_mode_t::NONE;
}

bilbo_position_control_data_t BILBO_PositionControl::get_data() {
	return this->_data;
}

void BILBO_PositionControl::_on_command_finished() {

	// Stop execution and reset internal state.
	if (this->current_mode
			== bilbo_position_control_mode_t::POSITION_TO_POINT) {
		send_info("Position command %u to (%.1f %.1f) finished",
				this->_current_element_id,
				this->_current_position_command.position_ref.x_target,
				this->_current_position_command.position_ref.y_target);
	} else if (this->current_mode
			== bilbo_position_control_mode_t::TURN_TO_HEADING) {
		send_info("Heading command %u to %.1f rad finished",
				this->_current_element_id,
				this->_current_heading_command.heading_ref.psi_target);
	}

	// Fire finished callback with element id
	this->callbacks.element_finished.call(this->_current_element_id);

	// Stop execution + clear internal state
	this->current_mode = bilbo_position_control_mode_t::NONE;

	this->_position_integral_error = 0.0f;
	this->_angle_integral_error = 0.0f;

	this->_arrival_hold_time = 0.0f;
	this->_was_inside_arrival_region = false;

	this->_current_element_id = 0;
}

void BILBO_PositionControl::_on_timeout() {

	// Stop execution and reset internal state.
	if (this->current_mode
			== bilbo_position_control_mode_t::POSITION_TO_POINT) {
		send_info("Position command %u to (%.1f %.1f) timed out!",
				this->_current_element_id,
				this->_current_position_command.position_ref.x_target,
				this->_current_position_command.position_ref.y_target);
	} else if (this->current_mode
			== bilbo_position_control_mode_t::TURN_TO_HEADING) {
		send_info("Heading command %u to %.1f rad timed out!",
				this->_current_element_id,
				this->_current_heading_command.heading_ref.psi_target);
	}

	// Fire timeout callback with element id
	this->callbacks.element_timeout.call(this->_current_element_id);
	// Timeout hook: abort current element and reset internals.
	this->abort_current_command();

	this->_position_integral_error = 0.0f;
	this->_angle_integral_error = 0.0f;

	this->_arrival_hold_time = 0.0f;
	this->_was_inside_arrival_region = false;

	this->_current_element_id = 0;
}

/**
 * @brief POSITION_TO_POINT controller (carrot chasing) that outputs (v, w).
 *
 * Improvements vs old version:
 *  - Completion uses distance-only (no heading-to-target check) to avoid noisy atan2 near goal.
 *  - v scaling uses cos(e_psi) but clamps to >= 0 so v never flips sign due to heading error.
 *  - w command is faded down near the goal so we don't “spin jitter” when dist is tiny.
 */
bilbo_position_control_output_t BILBO_PositionControl::_position_control_to_point(
		bilbo_position_state_t current_state, float x_target, float y_target,
		float max_speed_forward_override) {

	constexpr float PI = 3.14159265358979323846f;
	const float Ts = this->config.Ts;

	// Resolve forward speed limit
	float v_max =
			(max_speed_forward_override > 0.0f) ?
					max_speed_forward_override : this->config.max_speed_forward;
	v_max = std::max(0.0f, v_max);

	// Turn speed limit from config
	float w_max = std::max(0.0f, this->config.max_speed_turn);

	// Vector to goal
	const float dx = x_target - current_state.x;
	const float dy = y_target - current_state.y;
	const float dist = hypotf_safe(dx, dy);

	// Heading to the target point (only used for reverse selection, not for completion)
	const float angle_to_target = std::atan2(dy, dx);
	const float e_psi_to_target = wrapToPi(angle_to_target - current_state.psi);

	// Decide whether to allow driving backwards
	bool reverse_mode = false;
	if (this->config.allow_reverse) {
		if (std::fabs(e_psi_to_target) > this->config.backwards_switch_angle) {
			reverse_mode = true;
		}
	}

	// --- Carrot (lookahead) point computation ---
	const float look = std::max(0.0f, this->config.lookahead_distance);
	float cx = x_target;
	float cy = y_target;

	if (dist > 1e-6f && look > 1e-6f) {
		const float step_back = std::max(0.0f, dist - look);
		const float invd = 1.0f / (dist + 1e-9f);
		cx = x_target - dx * invd * step_back;
		cy = y_target - dy * invd * step_back;
	}

	// Desired heading toward carrot
	float psi_carrot = std::atan2(cy - current_state.y, cx - current_state.x);

	// In reverse mode, we want to "face away" from the carrot and drive backwards.
	if (reverse_mode) {
		psi_carrot = wrapToPi(psi_carrot + PI);
	}

	// Heading error used for angular control and speed scaling
	const float e_psi = wrapToPi(psi_carrot - current_state.psi);

	// ---------------- Linear PI (distance) ----------------
	const float v_pi_unsat = this->config.kp_linear * dist
			+ this->_position_integral_error;

	const float v_pi_sat =
			(v_max > 0.0f) ? clampf(v_pi_unsat, -v_max, v_max) : 0.0f;

	// Anti-windup (conditional integration)
	{
		const bool saturated = (std::fabs(v_pi_unsat - v_pi_sat) > 1e-6f);
		const float err = dist; // always >= 0
		const bool would_push_further = (saturated && (v_pi_unsat > v_pi_sat)
				&& (err > 0.0f));

		if (!would_push_further) {
			this->_position_integral_error += this->config.ki_linear * err * Ts;
		}
	}

	// Speed scaling by cos(e_psi) to avoid charging forward while misaligned.
	// IMPORTANT: clamp to >= 0 so we never flip direction due to heading error near goal.
	float cos_scale = std::cos(e_psi);
	if (cos_scale < 0.0f) {
		cos_scale = 0.0f;
	}

	float v_cmd = v_pi_sat * cos_scale;

	// If reverse_mode, we already made psi_carrot point "backwards".
	// That means cos(e_psi) scales correctly; now command negative forward speed.
	if (reverse_mode) {
		v_cmd = -v_cmd;
	}

	// ---------------- Angular PI (heading) ----------------
	const float w_pi_unsat = this->config.kp_angular * e_psi
			+ this->_angle_integral_error;
	const float w_pi_sat =
			(w_max > 0.0f) ? clampf(w_pi_unsat, -w_max, w_max) : 0.0f;

	// Anti-windup (conditional integration)
	{
		const bool saturated = (std::fabs(w_pi_unsat - w_pi_sat) > 1e-6f);
		const float err = e_psi;
		const bool would_push_further = (saturated
				&& ((w_pi_unsat > w_pi_sat && err > 0.0f)
						|| (w_pi_unsat < w_pi_sat && err < 0.0f)));

		if (!would_push_further) {
			this->_angle_integral_error += this->config.ki_angular * err * Ts;
		}
	}

	// Fade out turning near the goal to avoid jitter when dist is tiny and atan2 is noisy.
	// Use a radius based on the existing arrival tolerance so you don't need new config fields.
	// Within ~2*tolerance, w is reduced to 0 at the goal.
	const float fade_radius = std::max(1e-4f, 2.0f * this->config.distance_arrival_tolerance);
	const float w_fade = clampf(dist / fade_radius, 0.0f, 1.0f);

	const float w_cmd = w_pi_sat * w_fade;

	// ---------------- Completion detection ----------------
	// IMPORTANT CHANGE: distance-only completion.
	// Requiring heading-to-target near goal makes atan2 extremely sensitive and causes “spin jitter”.
	const bool inside = (dist <= this->config.distance_arrival_tolerance);

	if (inside) {
		this->_arrival_hold_time += Ts;
		this->_was_inside_arrival_region = true;
	} else {
		this->_arrival_hold_time = 0.0f;
		this->_was_inside_arrival_region = false;
	}

	bilbo_position_control_output_t out;
	out.v_cmd = v_cmd;
	out.psi_dot_cmd = w_cmd;
	return out;
}

/**
 * @brief TURN_TO_HEADING controller that outputs (0, w).
 *
 * Anti-windup:
 *  - Conditional integration when w saturates.
 *
 * Completion:
 *  - inside if |heading_error| <= angle_arrival_tolerance
 *  - must stay inside continuously for arrival_time seconds.
 */
bilbo_position_control_output_t BILBO_PositionControl::_turn_to_heading(
		bilbo_position_state_t current_state, float psi_target,
		float max_turn_speed_override) {

	const float Ts = this->config.Ts;

	float w_max =
			(max_turn_speed_override > 0.0f) ?
					max_turn_speed_override : this->config.max_speed_turn;
	w_max = std::max(0.0f, w_max);

	const float e_psi = wrapToPi(psi_target - current_state.psi);

	const float w_pi_unsat = this->config.kp_angular * e_psi
			+ this->_angle_integral_error;
	const float w_pi_sat =
			(w_max > 0.0f) ? clampf(w_pi_unsat, -w_max, w_max) : 0.0f;

	// Anti-windup (conditional integration)
	{
		const bool saturated = (std::fabs(w_pi_unsat - w_pi_sat) > 1e-6f);
		const float err = e_psi;
		const bool would_push_further = (saturated
				&& ((w_pi_unsat > w_pi_sat && err > 0.0f)
						|| (w_pi_unsat < w_pi_sat && err < 0.0f)));

		if (!would_push_further) {
			this->_angle_integral_error += this->config.ki_angular * err * Ts;
		}
	}

	// Completion detection: only angular tolerance
	const bool inside = (std::fabs(e_psi)
			<= this->config.angle_arrival_tolerance);

	if (inside) {
		this->_arrival_hold_time += Ts;
		this->_was_inside_arrival_region = true;
	} else {
		this->_arrival_hold_time = 0.0f;
		this->_was_inside_arrival_region = false;
	}

	bilbo_position_control_output_t out;
	out.v_cmd = 0.0f;
	out.psi_dot_cmd = w_pi_sat;
	return out;
}
