/*
 * firmware.h
 *
 *  Created on: Jul 10, 2022
 *      Author: Dustin Lehmann
 */

#ifndef FIRMWARE_CPP_H_
#define FIRMWARE_CPP_H_

#include <ws2812.h>
#include "buzzer.h"
#include "firmware_config.h"
#include "led.h"
#include "elapsedMillis.h"
#include "eeprom.h"
#include "registers.h"
#include "i2c_slave.h"



void checkUsb();

void checkSD();
void set_rgb_led_data(WS2812_LED *led, uint8_t reg_config, uint8_t reg_red,
		uint8_t reg_green, uint8_t reg_blue, uint8_t reg_blink_time,
		uint8_t reg_blink_counter);
void updateInternRGBLEDsFromRegisters();
void updateBuzzerFromRegisters();
void updateStatusLEDFromRegisters();

#endif /* FIRMWARE_C_H_ */
