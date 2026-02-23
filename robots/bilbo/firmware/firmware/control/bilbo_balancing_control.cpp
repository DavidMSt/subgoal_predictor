/*
 * bilbo_control.cpp
 *
 *  Created on: 22 Feb 2023
 *      Author: Dustin Lehmann
 */

#include <bilbo_balancing_control.h>

BILBO_BalancingControl::BILBO_BalancingControl() {
	this->mode = bilbo_balancing_control_mode_t::OFF;
	this->status = bilbo_balancing_control_status_t::NONE;
}

/* ========================================================================= */
void BILBO_BalancingControl::init(bilbo_balancing_control_config_t config) {
	this->config = config;
	this->status = bilbo_balancing_control_status_t::IDLE;
}

/* ========================================================================= */
void BILBO_BalancingControl::start() {
	if (this->status == bilbo_balancing_control_status_t::NONE
			|| this->status == bilbo_balancing_control_status_t::ERROR) {

//		setError();
//		bilbo_error_handler(BILBO_BALANCING_CONTROL_ERROR_INIT);
	}
	this->status = bilbo_balancing_control_status_t::RUNNING;
}

/* ========================================================================= */
bilbo_balancing_control_output_t BILBO_BalancingControl::update(
		bilbo_estimation_state_t state, bilbo_balancing_control_input_t input) {
	bilbo_balancing_control_output_t output = { 0, 0 };
	switch (this->status) {
	case bilbo_balancing_control_status_t::NONE: {
		output.u_1 = 0;
		output.u_2 = 0;
		break;
	}
	case bilbo_balancing_control_status_t::IDLE: {
		output.u_1 = 0;
		output.u_2 = 0;
		break;
	}
	case bilbo_balancing_control_status_t::ERROR: {
		output.u_1 = 0;
		output.u_2 = 0;
		break;
	}
	case bilbo_balancing_control_status_t::RUNNING: {
		switch (this->mode) {
		case bilbo_balancing_control_mode_t::OFF: {
			output.u_1 = 0;
			output.u_2 = 0;
			break;
		}
		case bilbo_balancing_control_mode_t::DIRECT: {
			output.u_1 = input.u_1;
			output.u_2 = input.u_2;
			break;
		}
		case bilbo_balancing_control_mode_t::ON: {
			output = this->_calculateOutput(state, input);
		}
		}
	}
	}
	return output;
}
/* ========================================================================= */
bilbo_balancing_control_output_t BILBO_BalancingControl::_calculateOutput(bilbo_estimation_state_t state,
		bilbo_balancing_control_input_t input) {
	bilbo_balancing_control_output_t output = { 0, 0 };
	output.u_1 = this->config.K[0] * state.v + this->config.K[1] * state.theta
			+ this->config.K[2] * state.theta_dot
			+ this->config.K[3] * state.psi_dot;

	output.u_2 = this->config.K[4] * state.v + this->config.K[5] * state.theta
			+ this->config.K[6] * state.theta_dot
			+ this->config.K[7] * state.psi_dot;

	output.u_1 = output.u_1 + input.u_1;
	output.u_2 = output.u_2 + input.u_2;
	return output;
}
/* ========================================================================= */
void BILBO_BalancingControl::reset() {
//	this->stop();
//	this->start();
}
/* ========================================================================= */
void BILBO_BalancingControl::stop() {
	this->mode = bilbo_balancing_control_mode_t::OFF;
//	this->status = BILBO_BALANCING_CONTROL_STATUS_IDLE;
}
/* ========================================================================= */
void BILBO_BalancingControl::set_K(float K[8]) {
	memcpy(this->config.K, K, sizeof(float) * 8);
}
/* ========================================================================= */
void BILBO_BalancingControl::set_mode(bilbo_balancing_control_mode_t mode) {

	if (this->status == bilbo_balancing_control_status_t::ERROR) {
		return;
	}

	if (this->status == bilbo_balancing_control_status_t::NONE) {
		return;
	}
	this->mode = mode;
}

