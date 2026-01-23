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
#include "elapsedMillis.h"

#define MAX_LED 16
#define USE_BRIGHTNESS 0

#define TIMER_BASE_FREQUENCY 16000000
#define TIMER_ARR 39

#define WS2812_LONG_PULSE (uint32_t) (TIMER_ARR+1) * 0.72
#define WS2812_SHORT_PULSE (uint32_t) (TIMER_ARR+1) * 0.28

enum WS2812_LED_Mode {
	WS2812_LED_MODE_CONTINIOUS, WS2812_LED_MODE_BLINK
};

typedef struct WS2812_blink_config {
	int8_t counter;
	uint16_t on_time_ms;
}WS2812_blink_config;


class WS2812_LED {
public:
	WS2812_LED();
	WS2812_LED(uint8_t position);

	void setColor(uint8_t red, uint8_t green, uint8_t blue);

	void setMode(WS2812_LED_Mode mode);
	void setBlinkConfig(WS2812_blink_config config);
	void setBlinkConfig(uint16_t on_time_ms, int8_t counter);
	void setContiniousOutput(uint8_t output);
	void blink();

	void update();

	uint8_t strand_position;
	uint8_t red = 0;
	uint8_t green = 0;
	uint8_t blue = 0;

	WS2812_LED_Mode mode;
	WS2812_blink_config blink_config;
	uint8_t continious_output = 0;


	elapsedMillis blinkTimer;

	uint8_t led_data[3] = {0};
private:
	uint8_t blink_output;
	int8_t blink_counter;
};

class WS2812_Strand {
public:
	WS2812_Strand(TIM_HandleTypeDef *tim, uint32_t timer_channel);
	WS2812_Strand(TIM_HandleTypeDef *tim, uint32_t timer_channel,
			uint8_t num_led);

	void init();

	void update();
	void send();
	void reset();

	WS2812_LED led[MAX_LED];
	TIM_HandleTypeDef *tim;
	uint32_t timer_channel;

	volatile uint8_t datasent = 0;

	uint8_t num_led;
private:

	uint8_t led_data[MAX_LED][4];
	uint8_t pwm_data[(24 * MAX_LED) + 50];

	uint32_t data_index = 0;
};

void HAL_TIM_PWM_PulseFinishedCallback(TIM_HandleTypeDef *htim);

#endif /* WS2812_H_ */
