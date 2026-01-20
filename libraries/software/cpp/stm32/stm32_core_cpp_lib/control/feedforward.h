/*
 * feedforward.h
 *
 * Simple velocity feedforward for torque-offset speed control.
 *
 * Provides:
 *  - static term      :  tau_v = Kv * v_ref
 *  - accel term       :  tau_a = Ka * dv_ref/dt   (derivative computed from reference)
 *  - optional stiction:  tau_c = Kc * smooth_sign(v_ref)  (tanh smoothing)
 *  - optional slew-rate limiter on v_ref (recommended)
 *  - optional output saturation + output slew-rate limiter (optional but useful)
 *
 * Notes:
 *  - Derivative is computed from the (optionally) slew-limited reference to avoid noise.
 *  - This is intended to be added to your feedback term:
 *        tau_cmd = tau_balance + tau_ff + tau_pid
 *
 * Created on: Jan 13, 2026
 */

#ifndef CONTROL_FF_FEEDFORWARD_H_
#define CONTROL_FF_FEEDFORWARD_H_

#include <cstdint>
#include <type_traits>
#include <math.h>

//struct feedforward_config_t {
//    // ---- gains ----
//    float Kv = 0.0f;   // [torque / (m/s)]  (or your speed unit)
//    float Ka = 0.0f;   // [torque / (m/s^2)]
//    float Kc = 0.0f;   // [torque] stiction / Coulomb-ish term magnitude
//
//    float Ts = 0.01f;  // sampling time [s], must be > 0
//
//    // ---- v_ref slew rate limiting ----
//    uint8_t enable_vref_slew = 1;
//    float   vref_slew_rate = 0.0f;  // [m/s^2] max |dv_ref/dt|. If <=0 -> holds previous.
//
//    // ---- derivative filtering (optional) ----
//    // Filter applies to dv_ref (acceleration estimate), not velocity.
//    uint8_t enable_a_filter = 0;
//    float   Ta_filter = 0.0f;  // [s] 1st-order LPF time constant on dv_ref/dt
//
//    // ---- stiction smoothing ----
//    // Uses tanh(v / v0). Smaller v0 -> more like sign(), larger -> smoother near zero.
//    uint8_t enable_stiction = 0;
//    float   v0_stiction = 0.05f; // [m/s] smoothing width; must be > 0
//
//    // ---- output saturation (optional) ----
//    uint8_t enable_output_limit = 0;
//    float   output_limit = 0.0f; // [torque], symmetric
//
//    // ---- output slew-rate limit (optional) ----
//    // Limits how fast tau_ff can change. Useful to avoid jerks when Kc or Ka is high.
//    uint8_t enable_output_slew = 0;
//    float   output_slew_rate = 0.0f; // [torque/s]
//
//    static constexpr feedforward_config_t zero() {
//        return feedforward_config_t{};
//    }
//};

struct feedforward_config_t {
	// ---- gains ----
	float Kv;   // [torque / (m/s)]
	float Ka;   // [torque / (m/s^2)]
	float Kc;   // [torque] stiction / Coulomb-ish term magnitude

	float Ts;   // sampling time [s], must be > 0

	// ---- v_ref slew rate limiting ----
	uint8_t enable_vref_slew;
	float vref_slew_rate;  // [m/s^2] max |dv_ref/dt|

	// ---- derivative filtering (optional) ----
	uint8_t enable_a_filter;
	float Ta_filter;       // [s] LPF time constant on dv_ref/dt

	// ---- stiction smoothing ----
	uint8_t enable_stiction;
	float v0_stiction;     // [m/s] smoothing width; must be > 0

	// ---- output saturation (optional) ----
	uint8_t enable_output_limit;
	float output_limit;    // [torque], symmetric

	// ---- output slew-rate limit (optional) ----
	uint8_t enable_output_slew;
	float output_slew_rate; // [torque/s]

	// Zero-init helper (keeps type trivial)
	static constexpr feedforward_config_t zero() {
		return feedforward_config_t { };
	}
};

static_assert(std::is_trivially_copyable_v<feedforward_config_t>);

class Feedforward {
public:
	Feedforward();
	explicit Feedforward(const feedforward_config_t &cfg);

	void reset();
	void set_config(const feedforward_config_t &cfg);

	// Update using desired velocity reference (v_ref).
	// Returns feedforward torque command tau_ff.
	float update(float v_ref);

	// Debug/telemetry accessors
	float get_vref_limited() const {
		return vref_limited_;
	}
	float get_dvref_dt() const {
		return dvref_dt_;
	}          // (possibly filtered) accel estimate
	float get_last_output() const {
		return last_output_;
	}

	feedforward_config_t config;

private:
	float vref_limited_ = 0.0f;  // internal v_ref after slew limiting
	float vref_last_ = 0.0f;     // last limited v_ref (for derivative)
	float dvref_dt_ = 0.0f;      // accel estimate (optionally filtered)
	float last_output_ = 0.0f;   // last tau_ff after limiting

private:
	static inline float clampf(float v, float lo, float hi) {
		return (v < lo) ? lo : ((v > hi) ? hi : v);
	}

	float apply_vref_slew(float v_ref);
	float compute_accel(float vref_now);

	float stiction_term(float vref_now) const;

	float apply_output_limit(float tau) const;
	float apply_output_slew(float tau);
};

#endif /* CONTROL_FF_FEEDFORWARD_H_ */
