/*
 * firmware.cpp
 *
 *  Created on: Jul 10, 2022
 *      Author: Dustin Lehmann
 */

#include "main.h"
#include "firmware_c.h"
#include "firmware_cpp.h"

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
		updateInternRGBLEDsFromRegisters();
		updateStatusLEDFromRegisters();
		update_external_rgb_led();

//
		neopixel_extern.update();
		neopixel_extern.send();
		HAL_Delay(10);
		neopixel_intern.update();
		neopixel_intern.send();

	}

	if (timer_buzzer >= 10) {
		timer_buzzer = 0;
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
	int8_t status = (int8_t) register_map[REG_ERROR_LED_CONFIG];

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
			register_map[REG_STATUS_RGB_LED_1_CONFIG],
			register_map[REG_STATUS_RGB_LED_1_RED],
			register_map[REG_STATUS_RGB_LED_1_GREEN],
			register_map[REG_STATUS_RGB_LED_1_BLUE],
			register_map[REG_STATUS_RGB_LED_1_BLINK_TIME],
			register_map[REG_STATUS_RGB_LED_1_BLINK_COUNTER]);
	set_rgb_led_data(&neopixel_intern.led[1],
			register_map[REG_STATUS_RGB_LED_2_CONFIG],
			register_map[REG_STATUS_RGB_LED_2_RED],
			register_map[REG_STATUS_RGB_LED_2_GREEN],
			register_map[REG_STATUS_RGB_LED_2_BLUE],
			register_map[REG_STATUS_RGB_LED_2_BLINK_TIME],
			register_map[REG_STATUS_RGB_LED_2_BLINK_COUNTER]);
	set_rgb_led_data(&neopixel_intern.led[2],
			register_map[REG_STATUS_RGB_LED_3_CONFIG],
			register_map[REG_STATUS_RGB_LED_3_RED],
			register_map[REG_STATUS_RGB_LED_3_GREEN],
			register_map[REG_STATUS_RGB_LED_3_BLUE],
			register_map[REG_STATUS_RGB_LED_3_BLINK_TIME],
			register_map[REG_STATUS_RGB_LED_3_BLINK_COUNTER]);


	register_map[REG_STATUS_RGB_LED_1_BLINK_COUNTER] = 0;
	register_map[REG_STATUS_RGB_LED_2_BLINK_COUNTER] = 0;
	register_map[REG_STATUS_RGB_LED_3_BLINK_COUNTER] = 0;
}

void updateBuzzerFromRegisters() {
	uint8_t reg_config = register_map[REG_BUZZER_CONFIG];
	uint8_t reg_data = register_map[REG_BUZZER_DATA];
	uint8_t reg_freq = register_map[REG_BUZZER_FREQ];
	uint8_t reg_blink_time = register_map[REG_BUZZER_BLINK_TIME];
	uint8_t reg_blink_counter = register_map[REG_BUZZER_BLINK_COUNTER];

	rc_buzzer.setConfig((float) (reg_freq * 10),
			(uint16_t) (reg_blink_time * 10), reg_blink_counter);

	if (reg_data == 1) {
		register_map[REG_BUZZER_DATA] = 0;
		rc_buzzer.start();
	}

}

void update_external_rgb_led() {
	for (int i = 0; i < 16; ++i) {
		uint16_t base = REG_EXTERNAL_RGB_LED_1_CONFIG + (i * 6);
		uint8_t r = register_map[base + 1]; // RED
		uint8_t g = register_map[base + 2]; // GREEN
		uint8_t b = register_map[base + 3]; // BLUE

		neopixel_extern.led[i].continious_output = 1; // color only, no blinking
		neopixel_extern.led[i].setColor(r, g, b);
	}
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

