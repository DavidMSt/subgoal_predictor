/*
 * battery_adc.h
 *
 *  Created on: Sep 23, 2025
 *      Author: lehmann
 */

#ifndef ADC_BATTERY_ADC_H_
#define ADC_BATTERY_ADC_H_
#include "stm32l4xx_hal.h"

#define BATTERY_ADC_VOLTAGE_DIVIDER 11.0f // 100K and 10K resistor

typedef struct battery_adc_config_t {
	ADC_HandleTypeDef *hadc;
	uint32_t channel;
};

class Battery_ADC {
public:
	Battery_ADC();
	void init(battery_adc_config_t config);
	void start();

	void startConversion();

	battery_adc_config_t config;
	float battery_voltage = 0.0;
private:

};

#endif /* ADC_BATTERY_ADC_H_ */
