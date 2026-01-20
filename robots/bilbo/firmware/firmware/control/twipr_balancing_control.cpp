/*
 * twipr_control.cpp
 *
 *  Created on: 22 Feb 2023
 *      Author: Dustin Lehmann
 */

#include <twipr_balancing_control.h>

TWIPR_BalancingControl::TWIPR_BalancingControl() {
	this->mode = twipr_balancing_control_mode_t::OFF;
	this->status = twipr_balancing_control_status_t::NONE;
}

/* ========================================================================= */
void TWIPR_BalancingControl::init(twipr_balancing_control_config_t config) {
	this->config = config;
	this->status = twipr_balancing_control_status_t::IDLE;
}

/* ========================================================================= */
void TWIPR_BalancingControl::start() {
	if (this->status == twipr_balancing_control_status_t::NONE
			|| this->status == twipr_balancing_control_status_t::ERROR) {

//		setError();
//		twipr_error_handler(TWIPR_BALANCING_CONTROL_ERROR_INIT);
	}
	this->status = twipr_balancing_control_status_t::RUNNING;
}

/* ========================================================================= */
twipr_balancing_control_output_t TWIPR_BalancingControl::update(
		twipr_estimation_state_t state, twipr_balancing_control_input_t input) {
	twipr_balancing_control_output_t output = { 0, 0 };
	switch (this->status) {
	case twipr_balancing_control_status_t::NONE: {
		output.u_1 = 0;
		output.u_2 = 0;
		break;
	}
	case twipr_balancing_control_status_t::IDLE: {
		output.u_1 = 0;
		output.u_2 = 0;
		break;
	}
	case twipr_balancing_control_status_t::ERROR: {
		output.u_1 = 0;
		output.u_2 = 0;
		break;
	}
	case twipr_balancing_control_status_t::RUNNING: {
		switch (this->mode) {
		case twipr_balancing_control_mode_t::OFF: {
			output.u_1 = 0;
			output.u_2 = 0;
			break;
		}
		case twipr_balancing_control_mode_t::DIRECT: {
			output.u_1 = input.u_1;
			output.u_2 = input.u_2;
			break;
		}
		case twipr_balancing_control_mode_t::ON: {
			output = this->_calculateOutput(state, input);
		}
		}
	}
	}
	return output;
}
/* ========================================================================= */
twipr_balancing_control_output_t TWIPR_BalancingControl::_calculateOutput(twipr_estimation_state_t state,
		twipr_balancing_control_input_t input) {
	twipr_balancing_control_output_t output = { 0, 0 };
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
void TWIPR_BalancingControl::reset() {
//	this->stop();
//	this->start();
}
/* ========================================================================= */
void TWIPR_BalancingControl::stop() {
	this->mode = twipr_balancing_control_mode_t::OFF;
//	this->status = TWIPR_BALANCING_CONTROL_STATUS_IDLE;
}
/* ========================================================================= */
void TWIPR_BalancingControl::set_K(float K[8]) {
	memcpy(this->config.K, K, sizeof(float) * 8);
}
/* ========================================================================= */
void TWIPR_BalancingControl::set_mode(twipr_balancing_control_mode_t mode) {

	if (this->status == twipr_balancing_control_status_t::ERROR) {
		return;
	}

	if (this->status == twipr_balancing_control_status_t::NONE) {
		return;
	}
	this->mode = mode;
}

