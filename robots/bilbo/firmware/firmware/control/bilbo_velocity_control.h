/*
 * bilbo_velocity_control.h
 *
 *  Created on: Jan 11, 2026
 *      Author: lehmann
 */

#ifndef CONTROL_BILBO_VELOCITY_CONTROL_H_
#define CONTROL_BILBO_VELOCITY_CONTROL_H_

#include "pid.h"
#include "feedforward.h"

struct bilbo_velocity_control_config_t {
	pid_control_config_t pid_config_v;
	feedforward_config_t ff_config_v;
	pid_control_config_t pid_config_psi_dot;
	feedforward_config_t ff_config_psi_dot;
};

struct bilbo_velocity_control_command_t {
	float v;
	float psi_dot;
};

struct bilbo_velocity_control_output_t {
	float u_l;
	float u_r;
};

struct bilbo_velocity_control_sample_t {
	float v_meas;
	float psi_dot_meas;
	bilbo_velocity_control_output_t output;
	bilbo_velocity_control_command_t command;
};

class BILBO_VelocityControl {
public:

	BILBO_VelocityControl();

	bilbo_velocity_control_output_t update(
			const bilbo_velocity_control_command_t &command, const float v_meas,
			const float psi_dot_meas);

	void reset();
	void set_config(const bilbo_velocity_control_config_t &config);
	void set_config_forward_pid(const pid_control_config_t &config);
	void set_config_forward_ff(const feedforward_config_t &config);
	void set_config_turn_pid(const pid_control_config_t &config);
	void set_config_turn_ff(const feedforward_config_t &config);

	bilbo_velocity_control_sample_t get_sample();

	bilbo_velocity_control_config_t get_config() const {
		return this->config;
	}

	PID_Control pid_forward;
	Feedforward ff_forward;
	PID_Control pid_turn;
	Feedforward ff_turn;

	bilbo_velocity_control_config_t config;

	bilbo_velocity_control_sample_t sample;

};

#endif /* CONTROL_BILBO_VELOCITY_CONTROL_H_ */
