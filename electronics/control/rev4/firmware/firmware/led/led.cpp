/*
 * core_hardware_led.cpp
 *
 *  Created on: Jul 6, 2022
 *      Author: Dustin Lehmann
 */


#include "led.h"

LED::LED(GPIO_TypeDef* GPIOx, uint16_t PINx) {
	this->GPIOx = GPIOx;
	this->PINx = PINx;
}

void LED::on() {
	HAL_GPIO_WritePin(this->GPIOx, this->PINx, GPIO_PIN_SET);
}


void LED::off() {
	HAL_GPIO_WritePin(this->GPIOx, this->PINx, GPIO_PIN_RESET);
}

void LED::toggle() {
	HAL_GPIO_TogglePin(this->GPIOx, this->PINx);
}

uint8_t LED::getState(){
	HAL_GPIO_ReadPin(this->GPIOx, this->PINx);
}

