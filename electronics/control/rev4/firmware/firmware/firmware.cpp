/*
 * firmware.cpp
 *
 *  Created on: Jul 10, 2022
 *      Author: Dustin Lehmann
 */

#include "main.h"
#include "firmware_c.h"
#include "firmware_cpp.h"
#include <string.h>

WS2812_Strand neopixel_intern(FIRMWARE_NEOPIXEL_INTERN_TIM,
FIRMWARE_NEOPIXEL_INTERN_CHANNEL, 2);

WS2812_Strand neopixel_extern(FIRMWARE_NEOPIXEL_EXTERN_TIM,
FIRMWARE_NEOPIXEL_EXTERN_CHANNEL, 16);

Buzzer rc_buzzer(FIRMWARE_PWM_BUZZER_TIM, FIRMWARE_PWM_BUZZER_CHANNEL);

LED led_status(LED_STATUS_GPIO_Port, LED_STATUS_Pin);
LED led_error(LED_ERROR_GPIO_Port, LED_ERROR_Pin);

EEPROM eeprom_config(FIRMWARE_I2C_INTERN, BOARD_EEPROM_CONFIG_ADDRESS);

elapsedMillis timer_check = 1000;
elapsedMillis timer_led_update;
elapsedMillis timer_buzzer;

elapsedMillis timer_led_register_read;

uint8_t register_map[255] = { 0 };
I2C_Slave i2c_slave_cm4(&hi2c2, 0x02, register_map, 255);
I2C_Slave i2c_slave_intern(&hi2c1, 0x02, register_map, 255);

Battery_ADC battery_adc;

elapsedMillis timer_test = 10000;
elapsedMillis timer_battery_adc = 0;

// Previous state for external RGB LEDs (for change detection)
static uint8_t prev_extern_rgb[16][3] = {{0}};
static bool extern_rgb_initialized = false;
static elapsedMillis timer_extern_refresh;
#define EXTERN_REFRESH_INTERVAL_MS 500  // Force refresh every 500ms to recover from noise corruption

// Atomic snapshot of register_map to prevent torn reads from I2C ISR.
// The I2C slave ISR writes register_map byte-by-byte; without a snapshot,
// the main loop can read a partially-updated RGB triplet (e.g. old R, new G, old B).
static uint8_t reg_snapshot[255];

static void snapshot_registers() {
	__disable_irq();
	memcpy(reg_snapshot, register_map, sizeof(reg_snapshot));
	__enable_irq();
}

/* ================================================================================= */
void firmware_init() {

	battery_adc_config_t battery_adc_config = {
			.hadc = FIRMWARE_ADC,
			.channel = ADC_CHANNEL_8
	};

	battery_adc.init(battery_adc_config);
	battery_adc.start();

	neopixel_intern.init();
	neopixel_extern.init();

	neopixel_intern.update();
	neopixel_intern.send();

	neopixel_extern.update();
	neopixel_extern.send();

	i2c_slave_cm4.init();
	i2c_slave_cm4.start();

	i2c_slave_intern.init();
	i2c_slave_intern.start();

	HAL_GPIO_WritePin(ENABLE_CM4_GPIO_Port, ENABLE_CM4_Pin, GPIO_PIN_SET);

	neopixel_intern.led[1].continious_output = 1;
	neopixel_intern.led[1].setColor(0, 0, 100);
	neopixel_intern.led[1].blink_config.on_time_ms = 400;
	neopixel_intern.led[1].blink_config.counter = 1;
//
	neopixel_intern.led[0].continious_output = 1;
	neopixel_intern.led[0].setColor(100, 0, 0);
	neopixel_intern.led[0].blink_config.on_time_ms = 400;
	neopixel_intern.led[0].blink_config.counter = 10;

	for (int i = 0; i < 16; i++) {
		neopixel_extern.led[i].continious_output = 1;
		neopixel_extern.led[i].setColor(0, 0, 0);
	}

	rc_buzzer.config.frequency = 440;
	rc_buzzer.config.on_time_ms = 200;
	rc_buzzer.config.counter = 1;

	led_status.off();
//	rc_buzzer.start();

}

/* ================================================================================= */
void firmware_update() {

	if (timer_check >= 250) {
		timer_check.reset();
		checkUsb();
		checkSD();

//		led_error.toggle();
//		led_status.toggle();

	}

	if (timer_battery_adc >= 500) {
		timer_battery_adc = 0;
		battery_adc.startConversion();
		store_battery_voltage_in_registers(battery_adc.battery_voltage);
	}

	if (timer_led_update >= 50) {
		timer_led_update = 0;

		// Take atomic snapshot of register_map so all reads below see
		// a consistent state, even if I2C ISR writes mid-update.
		snapshot_registers();

		updateInternRGBLEDsFromRegisters();
		updateStatusLEDFromRegisters();
		bool extern_changed = update_external_rgb_led();

		// Force periodic refresh to recover from noise-corrupted WS2812 frames
		if (!extern_changed && timer_extern_refresh >= EXTERN_REFRESH_INTERVAL_MS) {
			extern_changed = true;
		}

		// Only update and send external LEDs if colors changed or refresh due
		if (extern_changed) {
			timer_extern_refresh = 0;
			neopixel_extern.update();
			neopixel_extern.send();
		}

		// Internal LEDs (status indicators) - always update for blink support
		neopixel_intern.update();
		neopixel_intern.send();

	}

	if (timer_buzzer >= 10) {
		timer_buzzer = 0;

		snapshot_registers();

		updateBuzzerFromRegisters();
		rc_buzzer.update();

	}

	if (timer_test >= 70) {
		timer_test.reset();
	}

}

/* ================================================================================= */
void checkUsb() {
}

/* ================================================================================= */
void checkSD() {
	if (HAL_GPIO_ReadPin(SD_CARD_SWITCH_GPIO_Port, SD_CARD_SWITCH_Pin) == 0) {
		HAL_GPIO_WritePin(ENABLE_SD_GPIO_Port, ENABLE_SD_Pin, GPIO_PIN_SET);
	} else {
		HAL_GPIO_WritePin(ENABLE_SD_GPIO_Port, ENABLE_SD_Pin, GPIO_PIN_RESET);
	}
}

/* ================================================================================= */
void updateStatusLEDFromRegisters() {
	int8_t status = (int8_t) reg_snapshot[REG_ERROR_LED_CONFIG];

	switch (status) {
	case -1:
		led_status.toggle();
		register_map[REG_ERROR_LED_CONFIG] = (uint8_t) led_status.getState();
		break;
	case 0:
		led_status.off();
		break;
	case 1:
		led_status.on();
		break;
	}
}

/* ================================================================================= */

void updateInternRGBLEDsFromRegisters() {
	set_rgb_led_data(&neopixel_intern.led[0],
			reg_snapshot[REG_STATUS_RGB_LED_1_CONFIG],
			reg_snapshot[REG_STATUS_RGB_LED_1_RED],
			reg_snapshot[REG_STATUS_RGB_LED_1_GREEN],
			reg_snapshot[REG_STATUS_RGB_LED_1_BLUE],
			reg_snapshot[REG_STATUS_RGB_LED_1_BLINK_TIME],
			reg_snapshot[REG_STATUS_RGB_LED_1_BLINK_COUNTER]);
	set_rgb_led_data(&neopixel_intern.led[1],
			reg_snapshot[REG_STATUS_RGB_LED_2_CONFIG],
			reg_snapshot[REG_STATUS_RGB_LED_2_RED],
			reg_snapshot[REG_STATUS_RGB_LED_2_GREEN],
			reg_snapshot[REG_STATUS_RGB_LED_2_BLUE],
			reg_snapshot[REG_STATUS_RGB_LED_2_BLINK_TIME],
			reg_snapshot[REG_STATUS_RGB_LED_2_BLINK_COUNTER]);
	set_rgb_led_data(&neopixel_intern.led[2],
			reg_snapshot[REG_STATUS_RGB_LED_3_CONFIG],
			reg_snapshot[REG_STATUS_RGB_LED_3_RED],
			reg_snapshot[REG_STATUS_RGB_LED_3_GREEN],
			reg_snapshot[REG_STATUS_RGB_LED_3_BLUE],
			reg_snapshot[REG_STATUS_RGB_LED_3_BLINK_TIME],
			reg_snapshot[REG_STATUS_RGB_LED_3_BLINK_COUNTER]);

	// Clear blink counters (acknowledge) in the real register map
	register_map[REG_STATUS_RGB_LED_1_BLINK_COUNTER] = 0;
	register_map[REG_STATUS_RGB_LED_2_BLINK_COUNTER] = 0;
	register_map[REG_STATUS_RGB_LED_3_BLINK_COUNTER] = 0;
}

void updateBuzzerFromRegisters() {
	uint8_t reg_config = reg_snapshot[REG_BUZZER_CONFIG];
	uint8_t reg_data = reg_snapshot[REG_BUZZER_DATA];
	uint8_t reg_freq = reg_snapshot[REG_BUZZER_FREQ];
	uint8_t reg_blink_time = reg_snapshot[REG_BUZZER_BLINK_TIME];
	uint8_t reg_blink_counter = reg_snapshot[REG_BUZZER_BLINK_COUNTER];

	rc_buzzer.setConfig((float) (reg_freq * 10),
			(uint16_t) (reg_blink_time * 10), reg_blink_counter);

	if (reg_data == 1) {
		register_map[REG_BUZZER_DATA] = 0;  // Acknowledge in the real register map
		rc_buzzer.start();
	}

}

bool update_external_rgb_led() {
	bool changed = false;

	// On first call, force an update
	if (!extern_rgb_initialized) {
		extern_rgb_initialized = true;
		changed = true;
	}

	for (int i = 0; i < 16; ++i) {
		uint16_t base = REG_EXTERNAL_RGB_LED_1_CONFIG + (i * 6);
		uint8_t r = reg_snapshot[base + 1]; // RED
		uint8_t g = reg_snapshot[base + 2]; // GREEN
		uint8_t b = reg_snapshot[base + 3]; // BLUE

		// Check if this LED's color changed
		if (r != prev_extern_rgb[i][0] ||
			g != prev_extern_rgb[i][1] ||
			b != prev_extern_rgb[i][2]) {
			changed = true;
			prev_extern_rgb[i][0] = r;
			prev_extern_rgb[i][1] = g;
			prev_extern_rgb[i][2] = b;
		}

		neopixel_extern.led[i].continious_output = 1; // color only, no blinking
		neopixel_extern.led[i].setColor(r, g, b);
	}

	return changed;
}

void set_rgb_led_data(WS2812_LED *led, uint8_t reg_config, uint8_t reg_red,
		uint8_t reg_green, uint8_t reg_blue, uint8_t reg_blink_time,
		uint8_t reg_blink_counter) {

	uint8_t config_mode = reg_config;

	WS2812_LED_Mode mode;
	switch (config_mode) {
	case 0: {
		mode = WS2812_LED_MODE_CONTINIOUS;
		break;
	}
	case 1: {
		mode = WS2812_LED_MODE_BLINK;
		break;
	}
	default: {
		mode = WS2812_LED_MODE_CONTINIOUS;
		break;
	}
	}

	// Set the Color based on the register entries
	led->setColor(reg_red, reg_green, reg_blue);

	if (led->mode == WS2812_LED_MODE_CONTINIOUS) {
		led->continious_output = (reg_config >> 7);

		if (mode == WS2812_LED_MODE_BLINK) {
			led->setBlinkConfig((uint16_t) reg_blink_time * 10, -1);
			led->blink();
		}

	} else if (led->mode == WS2812_LED_MODE_BLINK) {
		if (mode == WS2812_LED_MODE_CONTINIOUS) {
			led->setMode(mode);
			led->continious_output = (reg_config >> 7);
		}
	}

}


void store_battery_voltage_in_registers(float voltage){

	// Store the 4 Float bytes in the register map, starting with REG_BATTERY_VOLTAGE
	uint8_t* p = (uint8_t*) &voltage;
	for (int i = 0; i < 4; i++) {
		register_map[REG_BATTERY_VOLTAGE + i] = *(p + i);
	}
}

