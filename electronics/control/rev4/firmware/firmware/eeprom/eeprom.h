/*
 * eeprom.h
 *
 *  Created on: Jul 6, 2022
 *      Author: Dustin Lehmann
 */

#ifndef CORE_MEMORY_EEPROM_CORE_MEMORY_EEPROM_H_
#define CORE_MEMORY_EEPROM_CORE_MEMORY_EEPROM_H_

#include "stm32l4xx_hal.h"

class EEPROM {
public:
	EEPROM(I2C_HandleTypeDef *hi2c, uint8_t address);

	I2C_HandleTypeDef *hi2c;
	uint8_t address;

	void write(uint16_t memory_address, uint8_t *data, uint16_t len);
	void read(uint16_t memory_address, uint8_t *data, uint16_t len);

};

#endif /* CORE_MEMORY_EEPROM_CORE_MEMORY_EEPROM_H_ */
