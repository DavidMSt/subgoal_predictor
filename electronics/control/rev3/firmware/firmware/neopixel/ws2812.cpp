/*
 * ws2812.c
 *
 *  Created on: Feb 11, 2022
 *      Author: Dustin Lehmann
 */

#include <ws2812.h>

uint8_t num_neopixel = 0;
WS2812_Strand *neopixel_handler[2] = { 0 };

WS2812_LED::WS2812_LED() {
}

WS2812_LED::WS2812_LED(uint8_t position) {
	this->strand_position = position;
}

void WS2812_LED::setColor(uint8_t red, uint8_t green, uint8_t blue) {
	this->red = red;
	this->green = green;
	this->blue = blue;
}

void WS2812_LED::setMode(WS2812_LED_Mode mode) {
	if (this->mode == WS2812_LED_MODE_CONTINIOUS && mode == WS2812_LED_MODE_BLINK){
		this->blink();
	}
	this->mode = mode;
}
void WS2812_LED::setBlinkConfig(WS2812_blink_config config) {
	this->blink_config = config;
}

void WS2812_LED::setBlinkConfig(uint16_t on_time_ms, int8_t counter) {
	this->blink_config.on_time_ms = on_time_ms;
	this->blink_config.counter = counter;
}

void WS2812_LED::setContiniousOutput(uint8_t output) {
	this->continious_output = output;
}

void WS2812_LED::blink() {
	if (this->mode == WS2812_LED_MODE_CONTINIOUS){
		this->mode = WS2812_LED_MODE_BLINK;
		this->blink_output = !this->continious_output;
		this->blink_counter = this->blink_config.counter*2;
		this->blinkTimer.reset();
	}
}

void WS2812_LED::update() {

	if (this->mode == WS2812_LED_MODE_CONTINIOUS) {

		this->led_data[0] = this->green * this->continious_output;
		this->led_data[1] = this->red * this->continious_output;
		this->led_data[2] = this->blue * this->continious_output;

	} else if (this->mode == WS2812_LED_MODE_BLINK) {

		if (this->blinkTimer >= this->blink_config.on_time_ms){
			this->blinkTimer.reset();

			this->blink_output = !this->blink_output;
			if (this->blink_counter > 0){
				this->blink_counter--;

				if (this->blink_counter == 0){
					this->mode = WS2812_LED_MODE_CONTINIOUS;
					this->blink_output = this->continious_output;
				}
			}
		}

		this->led_data[0] = this->green * this->blink_output;
		this->led_data[1] = this->red * this->blink_output;
		this->led_data[2] = this->blue * this->blink_output;
	}
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

	for (int i = 0; i < this->num_led; i++) {
		this->led[i].strand_position = i;
	}

	this->datasent = 0;
	this->reset();
}

void WS2812_Strand::update() {
	this->data_index = 0;
	uint32_t color;

	for (int i = 0; i < this->num_led; i++) {
		this->led[i].update();
	}

	for (int i = 0; i < this->num_led; i++) {
		color = ((this->led[i].led_data[0] << 16)
				| (this->led[i].led_data[1] << 8) | (this->led[i].led_data[2]));

		for (int i = 23; i >= 0; i--) {
			if (color & (1 << i)) {
				this->pwm_data[this->data_index] = WS2812_LONG_PULSE;
			}

			else {
				this->pwm_data[this->data_index] = WS2812_SHORT_PULSE;
			}

			this->data_index++;
		}
	}

	for (int i = 0; i < 10; i++) {
		this->pwm_data[this->data_index] = 0;
		this->data_index++;
	}
}

void WS2812_Strand::send() {

	HAL_TIM_PWM_Start_DMA(this->tim, this->timer_channel,
			(uint32_t*) this->pwm_data, this->data_index);
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
