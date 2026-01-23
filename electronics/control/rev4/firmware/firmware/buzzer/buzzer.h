/*
 * buzzer.h
 *
 *  Created on: Jul 10, 2022
 *      Author: Dustin Lehmann
 */

#ifndef BUZZER_BUZZER_H_
#define BUZZER_BUZZER_H_

#include "stm32l431xx.h"
#include "elapsedMillis.h"


#define BUZZER_TIMER_BASE_FREQUENCY 32000000
#define BUZZER_TIMER_PSC 5


typedef struct Buzzer_config {
	float frequency;
	uint16_t on_time_ms;
	int8_t counter;
} Buzzer_config;


class Buzzer {
public:

	Buzzer(TIM_HandleTypeDef *tim, uint32_t channel);


	void start();
	void stop();


	void setConfig(Buzzer_config config);
	void setConfig(float frequency, uint16_t on_time_ms, int8_t counter);
	void update();


	Buzzer_config config;


	elapsedMillis buzzerTimer;

private:
	TIM_HandleTypeDef *tim;
	uint32_t channel;

	uint8_t pwm_on = 0;
	uint8_t output_state = 0;
	uint8_t counter = 0;

	void pwmStart();
	void pwmStop();
};

#endif /* BUZZER_BUZZER_H_ */
