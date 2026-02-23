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
FIRMWARE_NEOPIXEL_INTERN_CHANNEL, 3);
WS2812_Strand neopixel_extern(FIRMWARE_NEOPIXEL_EXTERN_TIM,
FIRMWARE_NEOPIXEL_EXTERN_CHANNEL, 16);

Buzzer rc_buzzer(FIRMWARE_PWM_BUZZER_TIM, FIRMWARE_PWM_BUZZER_CHANNEL);

LED led_status(LED_GPIO_Port, LED_Pin);
LED led_usb(LED_USB_GPIO_Port, LED_USB_Pin);

EEPROM eeprom_config(FIRMWARE_I2C_INTERN, BOARD_EEPROM_CONFIG_ADDRESS);

elapsedMillis timer_check = 1000;
elapsedMillis timer_led_update;

elapsedMillis timer_led_register_read;

uint8_t register_map[255] = { 0 };
I2C_Slave i2c_slave_cm4(&hi2c2, 0x02, register_map, 255);
I2C_Slave i2c_slave_intern(&hi2c1, 0x02, register_map, 255);

elapsedMillis timer_test = 10000;

/* ================================================================================= */
void firmware_init() {

	neopixel_intern.init();
	neopixel_extern.init();

	neopixel_intern.update();
	neopixel_intern.send();

	i2c_slave_cm4.init();
	i2c_slave_cm4.start();

	i2c_slave_intern.init();
	i2c_slave_intern.start();

	HAL_GPIO_WritePin(ENABLE_CM4_GPIO_Port, ENABLE_CM4_Pin, GPIO_PIN_SET);

	neopixel_intern.led[1].continious_output = 1;
	neopixel_intern.led[1].setColor(0, 0, 100);
	neopixel_intern.led[1].blink_config.on_time_ms = 400;
	neopixel_intern.led[1].blink_config.counter = 1;

	neopixel_intern.led[2].continious_output = 1;
	neopixel_intern.led[2].setColor(0, 100, 0);
	neopixel_intern.led[2].blink_config.on_time_ms = 400;
	neopixel_intern.led[2].blink_config.counter = 1;

	neopixel_intern.led[0].continious_output = 1;
	neopixel_intern.led[0].setColor(100, 0, 0);
	neopixel_intern.led[0].blink_config.on_time_ms = 400;
	neopixel_intern.led[0].blink_config.counter = 10;

	rc_buzzer.config.frequency = 440;
	rc_buzzer.config.on_time_ms = 500;
	rc_buzzer.config.counter = 2;

	led_status.on();
	rc_buzzer.start();


}

/* ================================================================================= */
void firmware_update() {

	if (timer_check >= 100) {
		timer_check.reset();
		checkUsb();
		checkSD();
	}

	if (timer_led_update >= 10) {
		timer_led_update = 0;
		updateInternRGBLEDsFromRegisters();
		updateStatusLEDFromRegisters();
		updateBuzzerFromRegisters();
		neopixel_intern.update();
		neopixel_intern.send();

		rc_buzzer.update();
	}

	if (timer_test >= 70) {
		timer_test.reset();
	}

}

/* ================================================================================= */
void checkUsb() {
	if (HAL_GPIO_ReadPin(DETECT_USB_GPIO_Port, DETECT_USB_Pin) == 1) {
		led_usb.on();
	} else {
		led_usb.off();
	}
}

/* ================================================================================= */
void checkSD() {
	if (HAL_GPIO_ReadPin(DETECT_SD_GPIO_Port, DETECT_SD_Pin) == 0) {
		HAL_GPIO_WritePin(ENABLE_SD_GPIO_Port, ENABLE_SD_Pin, GPIO_PIN_SET);
	} else {
		HAL_GPIO_WritePin(ENABLE_SD_GPIO_Port, ENABLE_SD_Pin, GPIO_PIN_RESET);
	}
}

/* ================================================================================= */
void updateStatusLEDFromRegisters(){
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

	rc_buzzer.setConfig((float) (reg_freq * 10), (uint16_t)(reg_blink_time * 10), reg_blink_counter);

	if(reg_data == 1){
		register_map[REG_BUZZER_DATA] = 0;
		rc_buzzer.start();
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


	if (led->mode == WS2812_LED_MODE_CONTINIOUS){
		led->continious_output  = (reg_config >> 7);

		if (mode == WS2812_LED_MODE_BLINK){
			led->setBlinkConfig((uint16_t) reg_blink_time * 10, -1);
			led->blink();
		}

	} else if(led->mode == WS2812_LED_MODE_BLINK) {
		if (mode == WS2812_LED_MODE_CONTINIOUS){
			led->setMode(mode);
			led->continious_output  = (reg_config >> 7);
		}
	}

}

