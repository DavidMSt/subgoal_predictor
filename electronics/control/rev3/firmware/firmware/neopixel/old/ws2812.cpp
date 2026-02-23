/*
 * ws2812.c
 *
 *  Created on: Feb 11, 2022
 *      Author: Dustin Lehmann
 */

#include <ws2812.h>

uint8_t num_neopixel = 0;
WS2812_Strand *neopixel_handler[2] = { 0 };

WS2812_LED::WS2812_LED(uint8_t position) {
	this->position = position;
}

void WS2812_LED::set(uint8_t red, uint8_t green, uint8_t blue) {
	this->red = red;
	this->green = green;
	this->blue = blue;
}

/* ================================================================================ */
WS2812_Strand::WS2812_Strand(TIM_HandleTypeDef *tim, uint32_t timer_channel) {
	this->tim = tim;
	this->timer_channel = timer_channel;
	this->num_led = MAX_LED;
}

WS2812_Strand::WS2812_Strand(TIM_HandleTypeDef *tim, uint32_t timer_channel,
		uint8_t num_led) {
	this->tim = tim;
	this->timer_channel = timer_channel;
	this->num_led = num_led;
}

void WS2812_Strand::init() {
	neopixel_handler[num_neopixel] = this;
	num_neopixel++;

	this->datasent = 0;
	this->reset();
}

void WS2812_Strand::set(uint8_t led, uint8_t red, uint8_t green, uint8_t blue) {
	this->led_data[led][0] = led;
	this->led_data[led][1] = green;
	this->led_data[led][2] = red;
	this->led_data[led][3] = blue;
}
void WS2812_Strand::send() {

	uint32_t index = 0;
	uint32_t color;

	for (int i = 0; i < MAX_LED; i++) {
		color = ((this->led_data[i][1] << 16) | (this->led_data[i][2] << 8)
				| (this->led_data[i][3]));

		for (int i = 23; i >= 0; i--) {
			if (color & (1 << i)) {
				this->pwm_data[index] = WS2812_LONG_PULSE;
			}

			else {
				this->pwm_data[index] = WS2812_SHORT_PULSE;
			}

			index++;
		}
	}

	for (int i = 0; i < 10; i++) {
		this->pwm_data[index] = 0;
		index++;
	}

	HAL_TIM_PWM_Start_DMA(this->tim, this->timer_channel,
			(uint32_t*) this->pwm_data, index);
	while (this->datasent == 0) {

	};
	this->datasent = 0;

}
void WS2812_Strand::reset() {
	for (int i = 0; i < MAX_LED; i++) {
		this->led_data[i][0] = i;
		this->led_data[i][1] = 0;
		this->led_data[i][2] = 0;
		this->led_data[i][3] = 0;
	}
	uint32_t init_data[4] = { 50, 0, 50, 0 };
	HAL_TIM_PWM_Start_DMA(this->tim, this->timer_channel, (uint32_t*) init_data,
			4);
	HAL_Delay(10);
}

void HAL_TIM_PWM_PulseFinishedCallback(TIM_HandleTypeDef *htim) {
	for (int i = 0; i < num_neopixel; i++) {
		if (htim == neopixel_handler[i]->tim) {
			HAL_TIM_PWM_Stop_DMA(neopixel_handler[i]->tim,
					neopixel_handler[i]->timer_channel);
			neopixel_handler[i]->datasent = 1;
		}
	}

}
