/*
 * pid.cpp
 *
 * Created on: Jan 10, 2026
 * Author: (based on Dustin Lehmann's original)
 */

#include "pid.h"

// ---------------------------- Implementation Notes ----------------------------
//
// Order of operations (typical, robust):
//  1) Compute P from current error
//  2) Compute D from error difference (optionally filtered)
//  3) Predict unsaturated output: u_unsat = P + I + D
//  4) Anti-windup rule: only integrate if u_unsat is NOT saturated
//     (simple "conditional integration", like your example)
//  5) Recompute u_unsat after possible I update
//  6) Apply output saturation
//  7) Apply output rate limiting
//
// Setpoint rate limiting (NEW):
//  - If enabled, internal setpoint state is ramped at a bounded rate.
//  - Controller then operates on: error = setpoint_limited - measurement
// -----------------------------------------------------------------------------

PID_Control::PID_Control() {
	this->config = pid_control_config_default();
	this->reset();
}



void PID_Control::reset() {
	i_term_ = 0.0f;
	error_last_ = 0.0f;
	d_error_filt_ = 0.0f;
	last_output_ = 0.0f;
	setpoint_limited_ = 0.0f;
}

float PID_Control::apply_output_limit(float u) const {
	if (!config.enable_output_limit) {
		return u;
	}
	const float lim = fabsf(config.output_limit);
	if (lim <= 0.0f) {
		// If enabled but limit <= 0, treat as "hard zero output".
		return 0.0f;
	}
	return clampf(u, -lim, +lim);
}

float PID_Control::apply_rate_limit(float u) {
	if (!config.enable_rate_limit) {
		return u;
	}

	const float Ts = config.Ts;
	if (Ts <= 0.0f) {
		return u; // cannot rate limit without valid Ts
	}

	const float rate = fabsf(config.rate_limit);
	if (rate <= 0.0f) {
		// If enabled but rate <= 0, output cannot change.
		return last_output_;
	}

	const float max_delta = rate * Ts;
	const float delta = u - last_output_;

	const float delta_limited = clampf(delta, -max_delta, +max_delta);
	return last_output_ + delta_limited;
}

float PID_Control::apply_setpoint_rate_limit(float setpoint) {
	// If disabled -> directly use setpoint
	if (!config.enable_setpoint_rate_limit) {
		setpoint_limited_ = setpoint;
		return setpoint_limited_;
	}

	const float Ts = config.Ts;
	if (Ts <= 0.0f) {
		setpoint_limited_ = setpoint;
		return setpoint_limited_;
	}

	const float rate = fabsf(config.setpoint_rate_limit);
	if (rate <= 0.0f) {
		// If enabled but rate <= 0, setpoint cannot change.
		// Keep previous limited setpoint.
		return setpoint_limited_;
	}

	// Limit setpoint increment per sample
	const float max_delta = rate * Ts;
	const float delta = setpoint - setpoint_limited_;

	const float delta_limited = clampf(delta, -max_delta, +max_delta);
	setpoint_limited_ += delta_limited;
	return setpoint_limited_;
}

float PID_Control::compute_derivative(float error) {
	const float Ts = config.Ts;
	if (Ts <= 0.0f) {
		return 0.0f;
	}

	// Raw discrete derivative of error
	const float d_error = (error - error_last_) / Ts;

	if (!config.enable_d_filter) {
		return d_error;
	}

	// 1st-order low-pass filter on d_error:
	//
	// y[k] = y[k-1] + alpha * (x[k] - y[k-1])
	//
	// alpha = Ts / (Td_filter + Ts)
	//
	const float T = config.Td_filter;
	if (T <= 0.0f) {
		// filter "disabled" via parameter
		return d_error;
	}

	const float alpha = Ts / (T + Ts);
	d_error_filt_ = d_error_filt_ + alpha * (d_error - d_error_filt_);
	return d_error_filt_;
}

float PID_Control::update(float error) {
	// Backwards compatible API: caller supplies error directly
	return update_from_error(error);
}

void PID_Control::set_config(const pid_control_config_t &config) {
	this->reset();
	this->config = config;
}

float PID_Control::update(float setpoint, float measurement) {
	// Recommended API:
	//  1) optionally rate limit setpoint
	//  2) compute error from (limited setpoint - measurement)
	const float sp = apply_setpoint_rate_limit(setpoint);
	const float error = sp - measurement;
	return update_from_error(error);
}

float PID_Control::update_from_error(float error) {
	const float Ts = config.Ts;
	if (Ts <= 0.0f) {
		// Invalid sample time -> safest is do nothing
		return last_output_;
	}

	// --- Compute P and D using current states ---
	const float p_term = config.Kp * error;
	const float d_term = config.Kd * compute_derivative(error);

	// --- Predict output BEFORE updating integrator (for anti-windup decision) ---
	float u_pred = p_term + i_term_ + d_term;

	// --- Output saturation check for anti-windup (simple conditional integration) ---
	bool saturated = false;
	if (config.enable_output_limit && fabsf(config.output_limit) > 0.0f) {
		const float lim = fabsf(config.output_limit);
		saturated = (u_pred > lim) || (u_pred < -lim);
	}

	// --- Update integrator ONLY when not saturated ---
	//
	// Requested behavior:
	//   "When we are in output limit we should also not integrate the i part further"
	//
	if (!saturated && config.Ki != 0.0f) {
		// Store I-term contribution directly:
		// I += Ki * e * Ts
		i_term_ += (config.Ki * error * Ts);

		// Optional I-term limit (in output units)
		if (config.enable_i_limit) {
			const float ilim = fabsf(config.i_term_limit);
			if (ilim > 0.0f) {
				i_term_ = clampf(i_term_, -ilim, +ilim);
			} else {
				// enabled but limit <= 0 => clamp to 0
				i_term_ = 0.0f;
			}
		}

		// Recompute predicted command using updated I
		u_pred = p_term + i_term_ + d_term;
	}

	// --- Apply output saturation ---
	float u = apply_output_limit(u_pred);

	// --- Apply output rate limiting (based on last output) ---
	u = apply_rate_limit(u);

	// --- Update states for next iteration ---
	error_last_ = error;
	last_output_ = u;

	return u;
}
