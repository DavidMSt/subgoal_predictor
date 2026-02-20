/*
 * bilbo_safety.cpp
 *
 *  Created on: Feb 22, 2023
 *      Author: lehmann_workstation
 */

#include "bilbo_supervisor.h"

const osThreadAttr_t safety_task_attributes = { .name = "safety", .stack_size =
		256 * 4, .priority = (osPriority_t) osPriorityNormal, };

elapsedMillis timerDriveTick;

/* ============================================================================= */
BILBO_Supervisor::BILBO_Supervisor() {

}

/* ============================================================================= */
void BILBO_Supervisor::init(bilbo_supervisor_config_t config) {
	this->config = config;
}

/* ============================================================================= */
void BILBO_Supervisor::start() {
	osThreadNew(startTwiprSupervisorTask, (void*) this,
			&safety_task_attributes);
}

/* ============================================================================= */
void BILBO_Supervisor::task() {
	timerDriveTick.reset();

	while (true) {

//		bilbo_supervisor_dings_t error;

//		// Check the motors
//		error = this->checkMotors();
//		if (error == BILBO_SUPERVISOR_MOTOR_TIMEOUT) {
//
//			// Stop the control module
//			this->config.control->stop();
//			this->setError(BILBO_ERROR_CRITICAL);
//			send_error("Motor timeout");
//		}
//		if (error == BILBO_SUPERVISOR_MOTOR_RACECONDITION_RESETS){
//			this->config.control->stop();
//			this->setError(BILBO_ERROR_CRITICAL);
//			send_error("Motor race conditions");
//		}
//		if (error == BILBO_SUPERVISOR_MOTOR_ERROR){
//			this->config.control->stop();
//			this->setError(BILBO_ERROR_CRITICAL);
//			send_error("Motor Error");
//		}

		// Check the motor speed
		this->checkMotorSpeed();

		// Check the motors
		this->checkMotors();

//		if (error == BILBO_SUPERVISOR_WHEEL_SPEED) {
//			// Stop the control module
//			this->config.control->stop();
//			this->setError(BILBO_ERROR_WARNING);
//			send_warning("Motor max speed detected");
//
//		}

		// Check the button
		this->checkButton();
//		if (error == BILBO_SUPERVISOR_MANUAL_STOP) {
//			// Stop the control module
//			this->config.control->stop();
//			this->setError(BILBO_ERROR_WARNING);
//			send_warning("Manual stop");
//		}

// Check if the robot is stuck
//		error = this->checkStuck();
//		if (error == BILBO_SUPERVISOR_STUCK) {
//			// Stop the control module
//			this->config.control->stop();
//			this->setError(BILBO_ERROR_WARNING);
//		}

// Check the controllers
//		error = this->checkControllers();
//		if (error == BILBO_SUPERVISOR_ERROR_INTEGRATOR_OVERRUN) {
//			// Stop the control module
//			this->config.control->stop();
//			this->setError(BILBO_ERROR_WARNING);
//		}
		osDelay(50);
	}
}

/* ============================================================================= */
void BILBO_Supervisor::checkMotors() {

//	if (timerDriveTick > 1000) {
//		timerDriveTick.reset();
//
//		if (this->config.drive->status == BILBO_DRIVE_STATUS_ERROR){
//			return BILBO_SUPERVISOR_MOTOR_ERROR;
//		}
//
//
//		if (!(this->config.drive->tick > this->lastDriveTick)) {
//
//			this->lastDriveTick = this->config.drive->tick;
//			return BILBO_SUPERVISOR_MOTOR_TIMEOUT;
//		} else {
//			this->lastDriveTick = this->config.drive->tick;
//			return BILBO_SUPERVISOR_NONE;
//		}
//
//	}
//	if (this->config.drive->race_conditions >=10){
//		return BILBO_SUPERVISOR_MOTOR_RACECONDITION_RESETS;
//	}

//	return BILBO_SUPERVISOR_NONE;
//	return BILBO_SUPERVISOR_NONE;
}

/* ============================================================================= */
void BILBO_Supervisor::checkMotorSpeed() {


	if (this->config.control->mode == bilbo_control_mode_t::OFF) {
		return;
	}

	bilbo_drive_speed_t speed = this->config.drive->getSpeed();
	if (std::fabs(speed.left) > this->config.max_wheel_speed
			|| std::fabs(speed.right) > this->config.max_wheel_speed) {

		// Stop the controller
		this->config.control->stop();

		// Set a warning in the Error Handler
		setError(BILBO_ERROR_WARNING, BILBO_WARNING_WHEEL_SPEED);
		send_warning("Max wheel speed detected");
	}
}

/* ============================================================================= */
void BILBO_Supervisor::checkButton() {

	if (this->config.off_button->check() == 0 && this->config.control->mode != bilbo_control_mode_t::OFF) {

		this->config.control->stop();
		setError(BILBO_ERROR_WARNING, BILBO_WARNING_MANUAL_STOP);
		send_warning("Manual Stop");
	}
}

/* ============================================================================= */
//bilbo_supervisor_dings_t BILBO_Supervisor::checkStuck() {
//
//	if (this->config.control->mode != BILBO_CONTROL_MODE_VELOCITY) {
//		this->stuck_data.is_stuck = false;
//		this->stuck_data.error_count = 0;
//		this->stuck_data.last_pitch_angle = 0;
//		this->stuck_data.last_velocity_error = 0;
//		return BILBO_SUPERVISOR_NONE;
//	}
//
//	float velocity_error = abs(
//			this->config.control->_external_input.u_velocity_forward
//					- this->config.estimation->state.v);
//	float pitch_angle_deviation = abs(
//			this->config.estimation->state.theta
//					- this->stuck_data.last_pitch_angle);
//
//	if (abs(velocity_error - this->stuck_data.last_velocity_error)
//			< this->config.stuck_config.max_velocity_error
//			&& pitch_angle_deviation
//					< this->config.stuck_config.max_pitch_angle_deviation) {
//		this->stuck_data.error_count++;
//	} else {
//		this->stuck_data.error_count = 0;
//	}
//
//	this->stuck_data.last_velocity_error = velocity_error;
//	this->stuck_data.last_pitch_angle = this->config.estimation->state.theta;
//
//	if (this->stuck_data.error_count
//			>= this->config.stuck_config.stuck_duration) {
//		this->stuck_data.is_stuck = true;
//		return BILBO_SUPERVISOR_STUCK;
//	}
//	this->stuck_data.is_stuck = false;
//	return BILBO_SUPERVISOR_NONE;
//
//}
/* ============================================================================= */
//bilbo_supervisor_dings_t BILBO_Supervisor::checkControllers() {
//
//	return BILBO_SUPERVISOR_NONE;
//
//}
/* ============================================================================= */
//bilbo_supervisor_dings_t BILBO_Supervisor::check() {
//	bilbo_error_type_t output = this->error;
//	this->error = BILBO_ERROR_NONE;
//	return output;
//}
///* ============================================================================= */
//void BILBO_Supervisor::sendWarning(bilbo_supervisor_error_t id,
//		bilbo_error_t error, const char *message, uint8_t len) {
//
//	warning_message.data->error = error;
//	strncpy(warning_message.data->text, message, len);
//	warning_message.data->text[len + 1] = '\0';
//	this->config.communication->sendMessage(warning_message);
//}
/* ============================================================================= */
//void BILBO_Supervisor::setError(bilbo_error_type_t error) {
//	if (error > this->error) {
//		this->error = error;
//	}
//}
/* ============================================================================= */
void startTwiprSupervisorTask(void *args) {

	BILBO_Supervisor *argument = (BILBO_Supervisor*) args;
	argument->task();

}
