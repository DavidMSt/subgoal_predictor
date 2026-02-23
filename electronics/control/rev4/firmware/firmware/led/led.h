/*
 * core_hardware_led.hpp
 *
 *  Created on: Jul 6, 2022
 *      Author: Dustin Lehmann
 */

#ifndef CORE_HARDWARE_LED_CORE_HARDWARE_LED_H_
#define CORE_HARDWARE_LED_CORE_HARDWARE_LED_H_

#include "stm32l4xx_hal.h"

class LED {
public:
	LED(GPIO_TypeDef* GPIOx, uint16_t PINx);
	GPIO_TypeDef* GPIOx;
	uint16_t PINx;

	void on();
	void off();
	void toggle();
	uint8_t getState();

};



#endif /* CORE_HARDWARE_LED_CORE_HARDWARE_LED_H_ */
