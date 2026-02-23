/*
 * firmware.cpp
 *
 *  Created on: Jan 4, 2025
 *      Author: lehmann
 */

#include "main.h"
#include "firmware_c.h"
#include "firmware.h"

void firmware() {

}

Firmware::Firmware() {

}

void Firmware::init() {

	i2c_slave_config_t i2c_config = { .mode = I2C_SLAVE_MODE_IT,
			.address = 0x04, .registerMap = this->register_map, .num_registers =
					255, };

	this->i2c_slave.init(i2c_config);
	this->i2c_slave.callbacks.listen_cmplt_callback.set(this,
			&Firmware::i2c_slave_receive_callback);
}

void Firmware::start() {

}

void Firmware::task() {

	while (true) {
		if (updateTimer >= 250) {
			updateTimer.reset();
		}
	}
}

void Firmware::update() {

	// Check the charge state
	if (this->checkChargeState()) {
		this->setOutputs(0, 0, 0, 1);
	} else {
		this->setOutputs(1, 1, 1, 1);
	}
}

void Firmware::setOutputs(bool out1, bool out2, bool out3, bool out4) {

	HAL_GPIO_WritePin(OUT_1_PORT, OUT_1_PIN, bool_to_pinstate(out1));
	HAL_GPIO_WritePin(OUT_2_PORT, OUT_2_PIN, bool_to_pinstate(out2));
	HAL_GPIO_WritePin(OUT_3_PORT, OUT_3_PIN, bool_to_pinstate(out3));
	HAL_GPIO_WritePin(OUT_4_PORT, OUT_4_PIN, bool_to_pinstate(out4));
}

bool Firmware::checkChargeState() {
	if (HAL_GPIO_ReadPin(CHG_DETECT_PORT, CHG_DETECT_PIN)) {
		return false;
	} else {
		return true;
	}
}


float Firmware::measureCell(uint8_t cell){

}

void Firmware::i2c_slave_receive_callback(uint8_t address) {

	switch (address) {
	case REG_DEBUG_1: {
		break;
	}
	case REG_DEBUG_2: {
		break;
	}
	}

}

