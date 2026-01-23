/*
 * ws2812.h
 *
 *  Created on: Feb 11, 2022
 *      Author: Dustin Lehmann
 */

#ifndef WS2812_H_
#define WS2812_H_

#include "stm32g0xx_hal.h"
#include "math.h"

#define MAX_LED 16
#define USE_BRIGHTNESS 0



#define TIMER_BASE_FREQUENCY 16000000
#define TIMER_ARR 19


#define WS2812_LONG_PULSE (uint32_t) (TIMER_ARR+1) * 0.7
#define WS2812_SHORT_PULSE (uint32_t) (TIMER_ARR+1) * 0.3


enum WS2812_LED_Mode {
	WS2812_LED_MODE_CONTINIOUS, WS2812_LED_MODE_BLINK
};

class WS2812_Strand {
public:
	WS2812_Strand(TIM_HandleTypeDef* tim, uint32_t timer_channel);
	WS2812_Strand(TIM_HandleTypeDef* tim, uint32_t timer_channel, uint8_t num_led);

	void init();
	void set(uint8_t led, uint8_t red, uint8_t green, uint8_t blue);
	void send();
	void reset();


	TIM_HandleTypeDef* tim;
	uint32_t timer_channel;

	volatile uint8_t datasent = 0;
private:
	uint8_t num_led;
	uint8_t led_data[MAX_LED][4];
	uint8_t pwm_data[(24*MAX_LED)+50];
};



void HAL_TIM_PWM_PulseFinishedCallback(TIM_HandleTypeDef *htim);

#endif /* WS2812_H_ */
