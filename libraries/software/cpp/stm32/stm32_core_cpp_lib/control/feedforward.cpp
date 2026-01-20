/*
 * feedforward.cpp
 *
 * Created on: Jan 13, 2026
 */

#include "feedforward.h"

Feedforward::Feedforward() {
    // defaults already in struct
    reset();
}

Feedforward::Feedforward(const feedforward_config_t& cfg) {
    config = cfg;
    reset();
}

void Feedforward::set_config(const feedforward_config_t& cfg) {
    config = cfg;
    reset();
}

void Feedforward::reset() {
    vref_limited_ = 0.0f;
    vref_last_ = 0.0f;
    dvref_dt_ = 0.0f;
    last_output_ = 0.0f;
}

float Feedforward::apply_vref_slew(float v_ref) {
    if (!config.enable_vref_slew) {
        vref_limited_ = v_ref;
        return vref_limited_;
    }

    const float Ts = config.Ts;
    if (Ts <= 0.0f) {
        vref_limited_ = v_ref;
        return vref_limited_;
    }

    const float rate = fabsf(config.vref_slew_rate);
    if (rate <= 0.0f) {
        // If enabled but <=0, v_ref cannot change (hold).
        return vref_limited_;
    }

    const float max_delta = rate * Ts;      // max change per sample
    const float delta = v_ref - vref_limited_;
    const float delta_limited = clampf(delta, -max_delta, +max_delta);

    vref_limited_ += delta_limited;
    return vref_limited_;
}

float Feedforward::compute_accel(float vref_now) {
    const float Ts = config.Ts;
    if (Ts <= 0.0f) {
        return 0.0f;
    }

    // Raw acceleration estimate from (limited) reference
    const float a_raw = (vref_now - vref_last_) / Ts;

    if (!config.enable_a_filter) {
        dvref_dt_ = a_raw;
        return dvref_dt_;
    }

    // 1st order LPF: y += alpha (x - y), alpha = Ts/(T + Ts)
    const float T = config.Ta_filter;
    if (T <= 0.0f) {
        dvref_dt_ = a_raw;
        return dvref_dt_;
    }

    const float alpha = Ts / (T + Ts);
    dvref_dt_ = dvref_dt_ + alpha * (a_raw - dvref_dt_);
    return dvref_dt_;
}

float Feedforward::stiction_term(float vref_now) const {
    if (!config.enable_stiction || config.Kc == 0.0f) {
        return 0.0f;
    }

    float v0 = config.v0_stiction;
    if (v0 <= 0.0f) {
        // fallback to "hard" sign
        if (vref_now > 0.0f) return +config.Kc;
        if (vref_now < 0.0f) return -config.Kc;
        return 0.0f;
    }

    // Smooth sign to avoid chatter near zero:
    // s = tanh(v / v0)  -> in (-1, +1)
    const float s = tanhf(vref_now / v0);
    return config.Kc * s;
}

float Feedforward::apply_output_limit(float tau) const {
    if (!config.enable_output_limit) {
        return tau;
    }
    const float lim = fabsf(config.output_limit);
    if (lim <= 0.0f) {
        return 0.0f;
    }
    return clampf(tau, -lim, +lim);
}

float Feedforward::apply_output_slew(float tau) {
    if (!config.enable_output_slew) {
        return tau;
    }

    const float Ts = config.Ts;
    if (Ts <= 0.0f) {
        return tau;
    }

    const float rate = fabsf(config.output_slew_rate);
    if (rate <= 0.0f) {
        // cannot change
        return last_output_;
    }

    const float max_delta = rate * Ts;
    const float delta = tau - last_output_;
    const float delta_limited = clampf(delta, -max_delta, +max_delta);
    return last_output_ + delta_limited;
}

float Feedforward::update(float v_ref) {
    const float Ts = config.Ts;
    if (Ts <= 0.0f) {
        return last_output_;
    }

    // 1) Slew-limit reference (recommended to prevent immediate saturation/jerk)
    const float v_limited = apply_vref_slew(v_ref);

    // 2) Acceleration estimate from reference (clean signal)
    const float a_ref = compute_accel(v_limited);

    // 3) Compute FF components
    const float tau_v = config.Kv * v_limited;
    const float tau_a = config.Ka * a_ref;
    const float tau_c = stiction_term(v_limited);

    float tau = tau_v + tau_a + tau_c;

    // 4) Optional output saturation and output slew-rate limiting
    tau = apply_output_limit(tau);
    tau = apply_output_slew(tau);
    tau = apply_output_limit(tau); // re-apply in case slew pushes past limits

    // 5) Update state for next iteration
    vref_last_ = v_limited;
    last_output_ = tau;

    return tau;
}
