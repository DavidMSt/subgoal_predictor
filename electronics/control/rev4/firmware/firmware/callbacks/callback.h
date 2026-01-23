/*
 * core_utils_Callback.h
 *
 *  Created on: Jul 7, 2022
 *      Author: Dustin Lehmann
 */

#ifndef CORE_UTILS_CORE_UTILS_CALLBACK_H_
#define CORE_UTILS_CORE_UTILS_CALLBACK_H_

#include "stdint.h"

class core_utils_Callback {
public:
	core_utils_Callback();
	core_utils_Callback(void (*callback)(void *argument, void* params), void* params);
	void (*callback)(void *argument, void* params);
	void *params;

	void call(void *argument);

	uint8_t registered = 0;
private:

};




#endif /* CORE_UTILS_CORE_UTILS_CALLBACK_H_ */
