/*
 * adc.h
 *
 *  Created on: Jan 5, 2025
 *      Author: lehmann
 */

#ifndef ADC_ADC_H_
#define ADC_ADC_H_

#include "stm32l4xx.h"

typedef struct adc_config_t {
	ADC_HandleTypeDef* hadc;
}adc_config_t;


class ADC {
public:
	ADC();
	void init(adc_config_t config);

	uint32_t readChannel(uint32_t channel);

	adc_config_t config;

private:


};



#endif /* ADC_ADC_H_ */
