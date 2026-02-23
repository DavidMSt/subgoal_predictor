/*
 * elapsedMillis.cpp
 *
 *  Created on: Jul 12, 2022
 *      Author: Dustin Lehmann
 */

#include "elapsedMillis.h"

uint32_t millis() {
	return HAL_GetTick();
}



