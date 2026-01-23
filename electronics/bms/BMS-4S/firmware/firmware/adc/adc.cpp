/*
 * adc.cpp
 *
 *  Created on: Jan 5, 2025
 *      Author: lehmann
 */

#include "adc.h"

ADC::ADC() {

}

void ADC::init(adc_config_t config) {
	this->config = config;
}

uint32_t ADC::readChannel(uint32_t channel) {
	ADC_ChannelConfTypeDef sConfig = { 0 };

	sConfig.Channel = channel;
	sConfig.Rank = ADC_REGULAR_RANK_1;
	sConfig.SamplingTime = ADC_SAMPLETIME_12CYCLES_5;
	sConfig.SingleDiff = ADC_SINGLE_ENDED;

	HAL_ADC_ConfigChannel(this->config.hadc, &sConfig);

	HAL_ADC_Start(this->config.hadc);

	if (HAL_ADC_PollForConversion(this->config.hadc, HAL_MAX_DELAY) == HAL_OK) {
		uint32_t value = HAL_ADC_GetValue(this->config.hadc);
		HAL_ADC_Stop(this->config.hadc);
		return value;
	} else {
		HAL_ADC_Stop(this->config.hadc);
		return 0;
	}

}
