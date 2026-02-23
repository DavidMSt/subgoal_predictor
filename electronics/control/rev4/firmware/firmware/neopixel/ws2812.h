///*
// * ws2812.h
// *
// *  Created on: Feb 11, 2022
// *      Author: Dustin Lehmann
// */


/*
 * ws2812.h
 *
 *  Created on: Feb 11, 2022
 *      Author: Dustin Lehmann
 */

#ifndef WS2812_H_
#define WS2812_H_

#include "stm32l431xx.h"
#include "math.h"
#include "elapsedMillis.h"

#ifdef __cplusplus
extern "C" {
#endif
void HAL_TIM_PWM_PulseFinishedCallback(TIM_HandleTypeDef *htim);
#ifdef __cplusplus
}
#endif

// ===================== Configuration =====================

#define MAX_LED                 16
#define USE_BRIGHTNESS          0

// Timer config used for 800 kHz WS2812
// Core/timer clock: 32 MHz, PSC = 0, ARR = 39  ->  (ARR+1)/32e6 = 1.25 us per bit
#define TIMER_ARR               39

// High-time ticks for '1' and '0' at 32 MHz, ARR=39 (1.25 us/bit)
#define WS2812_T1H_TICKS        22  //26  // 0.8125 us high (spec: 0.65-0.95 us)
#define WS2812_T0H_TICKS        12   // 11 // 0.3438 us high (spec: 0.25-0.55 us)

// Reset latch tail in "bit slots" kept low (>= 50 us). 100 ~= 125 us.
#define WS2812_RESET_SLOTS      100

// Preamble: zero slots before LED data to ensure clean first-bit timing.
// 64 slots @ 1.25 us/slot = 80 us low before first real bit.
#define WS2812_PREAMBLE_SLOTS   100

// =========================================================

enum WS2812_LED_Mode {
	WS2812_LED_MODE_CONTINIOUS, WS2812_LED_MODE_BLINK
};

typedef struct WS2812_blink_config {
	int8_t counter;
	uint16_t on_time_ms;
} WS2812_blink_config;

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

	uint8_t strand_position = 0;
	uint8_t red = 0;
	uint8_t green = 0;
	uint8_t blue = 0;

	WS2812_LED_Mode mode = WS2812_LED_MODE_CONTINIOUS;
	WS2812_blink_config blink_config { 0, 0 };
	uint8_t continious_output = 1; // 1=on, 0=off

	elapsedMillis blinkTimer;

	// GRB order used by WS2812
	uint8_t led_data[3] = { 0, 0, 0 };

private:
	uint8_t blink_output = 0;
	int8_t blink_counter = 0;
};

class WS2812_Strand {
public:
	WS2812_Strand(TIM_HandleTypeDef *tim, uint32_t timer_channel);
	WS2812_Strand(TIM_HandleTypeDef *tim, uint32_t timer_channel,
			uint8_t num_led);

	void init();

	void update(); // prepares the PWM buffer (call whenever colors/state changed)
	void send();     // starts DMA transfer and waits for completion
	void reset();    // sends a long low period

	WS2812_LED led[MAX_LED];
	TIM_HandleTypeDef *tim;
	uint32_t timer_channel;

	volatile uint8_t datasent = 0;
	uint8_t num_led;

private:
	// Unused legacy scratch; kept for API compatibility
	uint8_t led_data[MAX_LED][4] = { { 0 } };

	// One CCR value per bit + reset tail (halfword-aligned for DMA)
	uint16_t pwm_data[WS2812_PREAMBLE_SLOTS + (24 * MAX_LED) + WS2812_RESET_SLOTS] = { 0 };

	uint32_t data_index = 0;
};

// Global registry so we can stop the right timer in the HAL callback
extern uint8_t num_neopixel;
extern WS2812_Strand *neopixel_handler[2];

#endif /* WS2812_H_ */
