/*
 * twipr_control.h
 *
 *  Created on: 22 Feb 2023
 *      Author: Dustin Lehmann
 */

#ifndef CONTROL_TWIPR_BALANCING_CONTROL_H_
#define CONTROL_TWIPR_BALANCING_CONTROL_H_

#include "firmware_core.h"
#include "twipr_estimation.h"

#define TWIPR_BALANCING_CONTROL_ERROR 0x00000601
#define TWIPR_BALANCING_CONTROL_ERROR_INIT 0x00000602

enum class twipr_balancing_control_mode_t: uint8_t {
	OFF = 0,
	DIRECT = 1,
	ON = 2,
};

enum class twipr_balancing_control_status_t: int8_t {
	NONE = 0,
	IDLE = 1,
	ERROR = -1,
	RUNNING = 2,
};

typedef enum twipr_balancing_control_callback_id_t {
	TWIPR_BALANCING_CONTROL_CALLBACK_ERROR = 1,
} twipr_balancing_control_callback_id_t;

typedef struct twipr_balancing_control_config_t {
	float K[8] = { 0 };
	float pitch_offset = 0;
} twipr_balancing_control_config_t;

typedef struct twipr_balancing_control_input_t {
	float u_1;
	float u_2;
} twipr_balancing_control_input_t;

typedef struct twipr_balancing_control_output_t {
	float u_1;
	float u_2;
} twipr_balancing_control_output_t;

class TWIPR_BalancingControl {
public:
	TWIPR_BalancingControl();
	void init(twipr_balancing_control_config_t config);
	void start();
	void reset();
	void stop();

	void registerCallback(twipr_balancing_control_callback_id_t callback_id,
			void (*callback)(void *argument, void *params), void *params);

	twipr_balancing_control_output_t update(twipr_estimation_state_t state,
			twipr_balancing_control_input_t input);

	void set_K(float K[8]);
	void set_mode(twipr_balancing_control_mode_t mode);

	twipr_balancing_control_status_t status;
	twipr_balancing_control_mode_t mode;
	twipr_balancing_control_config_t config;
private:

	twipr_balancing_control_output_t _calculateOutput(twipr_estimation_state_t state,
			twipr_balancing_control_input_t input);
	twipr_balancing_control_input_t _last_input;
	twipr_estimation_state_t _dynamic_state;
	twipr_estimation_state_t _last_dynamic_state;
	twipr_balancing_control_output_t _last_output;
};

#endif /* CONTROL_TWIPR_BALANCING_CONTROL_H_ */
