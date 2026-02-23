/*
 * eeprom.cpp
 *
 *  Created on: Jul 6, 2022
 *      Author: Dustin Lehmann
 */

#include "eeprom.h"

EEPROM::EEPROM(I2C_HandleTypeDef *hi2c,
		uint8_t address) {
	this->hi2c = hi2c;
	this->address = address;
}

void EEPROM::write(uint16_t memory_address, uint8_t *data,
		uint16_t len) {

	HAL_I2C_Mem_Write(this->hi2c, this->address, memory_address,
	I2C_MEMADD_SIZE_16BIT, data, len, 100);

}

void EEPROM::read(uint16_t memory_address, uint8_t *data,
		uint16_t len) {
	HAL_I2C_Mem_Read(this->hi2c, this->address, memory_address,
			I2C_MEMADD_SIZE_16BIT, data, len, 100);
}
