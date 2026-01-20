/*
 * pid.h
 *
 * Universal, easy-to-use PID controller with:
 *   - I-state stored as *I-term contribution* (Ki * e * Ts accumulated)
 *   - Optional derivative low-pass filter (1st order) with a single parameter
 *   - Symmetric output saturation with simple anti-windup (no integration in saturation)
 *   - Symmetric output rate limiter
 *   - Symmetric setpoint/target rate limiter (NEW)
 *
 * Created on: Jan 10, 2026
 * Author: (based on Dustin Lehmann's original)
 */

#ifndef CONTROL_PID_PID_H_
#define CONTROL_PID_PID_H_

#include <stdbool.h>
#include <math.h>

// ---------------------------- Configuration ----------------------------
//
// Notes on units:
//
// setpoint:       target value (rad, m, deg, etc.)
// measurement:    current value (same unit as setpoint)
// error:          setpoint - measurement
// output:         actuator command (torque, volts, PWM, ...)
//
// Kp:             output / error
// Ki:             output / (error * s)
// Kd:             output * s / error
//
// IMPORTANT CHANGE (requested):
//  The integrator state stores the *I-term contribution* directly:
//
//      I[k+1] = I[k] + Ki * e[k] * Ts
//
//  Therefore the control law is:
//
//      u = Kp*e + I + D
//
//  The integrator limit (i_term_limit) is in OUTPUT UNITS.
// ----------------------------------------------------------------------

#include <cstdint>
#include <type_traits>

struct pid_control_config_t {
    float Kp;
    float Ki;
    float Kd;

    float Ts;   // sampling time [s], must be > 0

    // -------- Integrator (I-term) limit --------
    uint8_t enable_i_limit;
    float   i_term_limit;

    // -------- Input saturation --------
    uint8_t enable_input_limit;
    float   input_limit;
    // -------- Output saturation --------
    uint8_t enable_output_limit;
    float   output_limit;

    // -------- Derivative filter --------
    uint8_t enable_d_filter;
    float   Td_filter;

    // -------- Output rate limiting --------
    uint8_t enable_rate_limit;
    float   rate_limit;

    // -------- Setpoint rate limiting --------
    uint8_t enable_setpoint_rate_limit;
    float   setpoint_rate_limit;

    // zero-init "constructor" while staying trivial
    static constexpr pid_control_config_t zero() {
        return pid_control_config_t{};
    }
};

static_assert(std::is_trivially_copyable_v<pid_control_config_t>);

constexpr pid_control_config_t pid_control_config_default() {
    pid_control_config_t c{};
    c.Ts = 0.01f;
    return c;
}

class PID_Control {
public:
    PID_Control();

    void reset();

    // -----------------------------------------------------------------
    // Update API #1: error-based update (backwards compatible)
    // Caller computes error = setpoint - measurement.
    // -----------------------------------------------------------------
    float update(float error);

    // -----------------------------------------------------------------
    // Update API #2: setpoint + measurement update (recommended)
    //
    // Internally:
    //   - optionally rate-limits the setpoint
    //   - computes error = setpoint_limited - measurement
    //   - runs PID on that error
    //
    // If setpoint rate limiting is disabled, setpoint_limited == setpoint.
    // -----------------------------------------------------------------
    float update(float setpoint, float measurement);

    void set_config(const pid_control_config_t& config);

    // Accessors (useful for debugging/telemetry)
    float get_i_term() const { return i_term_; }
    float get_last_output() const { return last_output_; }
    float get_setpoint_limited() const { return setpoint_limited_; }

    pid_control_config_t config;

private:
    // Stored I-term contribution (already includes Ki and Ts accumulation)
    float i_term_ = 0.0f;

    // Previous error for derivative
    float error_last_ = 0.0f;

    // Filtered derivative state (filtered d/dt of error)
    float d_error_filt_ = 0.0f;

    // Last output (after limiting), used for rate limiting
    float last_output_ = 0.0f;

    // Internal setpoint state (after optional rate limiting)
    float setpoint_limited_ = 0.0f;

private:
    static inline float clampf(float v, float lo, float hi) {
        return (v < lo) ? lo : ((v > hi) ? hi : v);
    }

    float apply_output_limit(float u) const;
    float apply_rate_limit(float u);
    float compute_derivative(float error);

    // NEW: setpoint limiter
    float apply_setpoint_rate_limit(float setpoint);

    // Shared internal implementation
    float update_from_error(float error);
};

#endif /* CONTROL_PID_PID_H_ */
