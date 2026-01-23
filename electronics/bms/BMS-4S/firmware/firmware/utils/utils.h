/*
 * utils.h
 *
 *  Created on: Jan 5, 2025
 *      Author: lehmann
 */

#ifndef UTILS_UTILS_H_
#define UTILS_UTILS_H_

#include "stm32l4xx_hal.h"


GPIO_PinState bool_to_pinstate(bool in){
	if (in){
		return GPIO_PIN_SET;
	} else {
		return GPIO_PIN_RESET;
	}
}




#endif /* UTILS_UTILS_H_ */
