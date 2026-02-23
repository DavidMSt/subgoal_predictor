/*
 * bilbo_velocity_control.cpp
 *
 *  Created on: Jan 11, 2026
 *      Author: lehmann
 *
 * Reworked on: Jan 13, 2026
 *
 * Changes:
 *  - Adds feedforward for forward velocity and yaw rate:
 *        u_forward = pid_forward(...) + ff_forward(...)
 *        u_turn    = pid_turn(...)    + ff_turn(...)
 *  - Initializes and applies FF configs
 *  - Stores additional telemetry in sample (including final outputs already present)
 *
 * Notes:
 *  - Signs: if your system needs negative torque for +v / +psi_dot, then FF gains Kv/Ka/Kc
 *    and PID gains Kp/Ki/Kd should be negative (given error = ref - meas and u adds to torque).
 */

#include "bilbo_velocity_control.h"

/* --------------------------------------------------------------------------------------------------------------- */
BILBO_VelocityControl::BILBO_VelocityControl() {
    // Make sure everything is in a defined state
    this->config = bilbo_velocity_control_config_t{
        .pid_config_v       = pid_control_config_default(),
        .ff_config_v        = feedforward_config_t::zero(),
        .pid_config_psi_dot = pid_control_config_default(),
        .ff_config_psi_dot  = feedforward_config_t::zero(),
    };

    // Apply configs
    this->pid_forward.set_config(this->config.pid_config_v);
    this->pid_turn.set_config(this->config.pid_config_psi_dot);

    this->ff_forward.set_config(this->config.ff_config_v);
    this->ff_turn.set_config(this->config.ff_config_psi_dot);

    this->reset();
}

/* --------------------------------------------------------------------------------------------------------------- */
void BILBO_VelocityControl::reset() {
    this->pid_forward.reset();
    this->pid_turn.reset();

    this->ff_forward.reset();
    this->ff_turn.reset();

    this->sample.output.u_l = 0.0f;
    this->sample.output.u_r = 0.0f;
    this->sample.v_meas = 0.0f;
    this->sample.psi_dot_meas = 0.0f;
    this->sample.command.v = 0.0f;
    this->sample.command.psi_dot = 0.0f;
}

/* --------------------------------------------------------------------------------------------------------------- */
void BILBO_VelocityControl::set_config(const bilbo_velocity_control_config_t &config) {
    this->reset();
    this->config = config;

    this->pid_forward.set_config(config.pid_config_v);
    this->pid_turn.set_config(config.pid_config_psi_dot);

    this->ff_forward.set_config(config.ff_config_v);
    this->ff_turn.set_config(config.ff_config_psi_dot);
}

/* --------------------------------------------------------------------------------------------------------------- */
void BILBO_VelocityControl::set_config_forward_pid(const pid_control_config_t &config) {
    this->reset();
    this->config.pid_config_v = config;
    this->pid_forward.set_config(config);
}

/* --------------------------------------------------------------------------------------------------------------- */
void BILBO_VelocityControl::set_config_forward_ff(const feedforward_config_t &config) {
    this->reset();
    this->config.ff_config_v = config;
    this->ff_forward.set_config(config);
}

/* --------------------------------------------------------------------------------------------------------------- */
void BILBO_VelocityControl::set_config_turn_pid(const pid_control_config_t &config) {
    this->reset();
    this->config.pid_config_psi_dot = config;
    this->pid_turn.set_config(config);
}

/* --------------------------------------------------------------------------------------------------------------- */
void BILBO_VelocityControl::set_config_turn_ff(const feedforward_config_t &config) {
    this->reset();
    this->config.ff_config_psi_dot = config;
    this->ff_turn.set_config(config);
}

/* --------------------------------------------------------------------------------------------------------------- */
bilbo_velocity_control_output_t BILBO_VelocityControl::update(
        const bilbo_velocity_control_command_t &command,
        const float v_meas,
        const float psi_dot_meas) {

    bilbo_velocity_control_output_t output{};

    // --- Feedforward terms (computed from references, optionally slew-limited inside FF) ---
    const float u_forward_ff = this->ff_forward.update(command.v);
    const float u_turn_ff    = this->ff_turn.update(command.psi_dot);

    // --- Feedback terms (PID) ---
    const float u_forward_pid = this->pid_forward.update(command.v, v_meas);
    const float u_turn_pid    = this->pid_turn.update(command.psi_dot, psi_dot_meas);

    // --- Sum FF + PID for each channel ---
    const float u_forward = u_forward_ff + u_forward_pid;
    const float u_turn    = u_turn_ff + u_turn_pid;

    // Convert (u_forward, u_turn) to (u_l, u_r)
    // Convention: u_turn > 0 => right wheel command bigger than left
    output.u_l = u_forward - u_turn;
    output.u_r = u_forward + u_turn;

    // --- Store sample/telemetry ---
    this->sample.output = output;
    this->sample.v_meas = v_meas;
    this->sample.psi_dot_meas = psi_dot_meas;
    this->sample.command = command;

    return output;
}

/* --------------------------------------------------------------------------------------------------------------- */
bilbo_velocity_control_sample_t BILBO_VelocityControl::get_sample() {
    return this->sample;
}
