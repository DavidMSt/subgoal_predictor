/*
 * buzzer.cpp
 *
 *  Created on: Jul 10, 2022
 *      Author: Dustin Lehmann
 */

#include "buzzer.h"

Buzzer::Buzzer(TIM_HandleTypeDef *tim, uint32_t channel) {
	this->tim = tim;
	this->channel = channel;
}

void Buzzer::pwmStart() {
	uint32_t arr = (uint32_t) (BUZZER_TIMER_BASE_FREQUENCY
			/ (this->config.frequency * BUZZER_TIMER_PSC + this->config.frequency)) - 1;

	HAL_TIM_PWM_Start(this->tim, this->channel);

	if (this->tim->Instance == TIM2) {

		__HAL_TIM_SetAutoreload(this->tim, (uint32_t) arr)
		;

		__HAL_TIM_SetCompare(this->tim,this->channel,(uint32_t) arr/2);

	} else {
		if (arr > 65535) {
			arr = 65535;
		}
		__HAL_TIM_SetAutoreload(this->tim, (uint16_t) arr)
		;

		__HAL_TIM_SetCompare(this->tim,this->channel,(uint16_t) arr/2);
	}
	this->pwm_on = 1;
}
void Buzzer::pwmStop() {
	HAL_TIM_PWM_Stop(this->tim, this->channel);
	this->pwm_on = 0;
}


void Buzzer::setConfig(Buzzer_config config) {
	this->config = config;
}
void Buzzer::setConfig(float frequency, uint16_t on_time_ms, int8_t counter) {
	this->config.frequency = frequency;
	this->config.on_time_ms = on_time_ms;
	this->config.counter = counter;
}

void Buzzer::start() {
	this->buzzerTimer.reset();
	this->output_state = 1;
	this->counter = this->config.counter * 2;
}

void Buzzer::stop() {
	this->counter = 0;
	this->output_state = 0;
}

void Buzzer::update() {
// TODO: continious buzzer
	if (this->counter > 0) {

		if (this->buzzerTimer >= this->config.on_time_ms) {
			this->buzzerTimer.reset();

			this->output_state = !this->output_state;
			this->counter--;

			if (this->counter == 0){
				this->output_state = 0;
			}
		}
	}

	if (this->output_state == 1 && this->pwm_on == 0) {
		this->pwmStart();
	} else if (this->output_state == 0 && this->pwm_on == 1) {
		this->pwmStop();
	}

//	if (this->counter > 0) {
//
//		if (buzzerTimer >= this->on_time) {
//			this->buzzerTimer.reset();
//
//			this->state = !this->state;
//
//			this->counter--;
//
//			if (this->counter == 0){
//				this->state = 0;
//			}
//		}
//	}
//
//	if (this->state && this->pwm_on == 0) {
//		this->start(this->frequency);
//	}
//
//	if (this->state == 0 && this->pwm_on) {
//		this->stop();
//	}

}
