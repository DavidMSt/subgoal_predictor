/*
 * battery_adc.cpp
 *
 *  Created on: Sep 23, 2025
 *      Author: lehmann
 */

#include "battery_adc.h"

Battery_ADC* battery_adc_instance = nullptr;
void adc_callback(ADC_HandleTypeDef* hadc);

Battery_ADC::Battery_ADC() {
	// TODO Auto-generated constructor stub
	battery_adc_instance = this;

}

void Battery_ADC::init(battery_adc_config_t config) {
	this->config = config;
	HAL_ADCEx_Calibration_Start(this->config.hadc, ADC_SINGLE_ENDED);
	HAL_ADC_RegisterCallback(this->config.hadc, HAL_ADC_CONVERSION_COMPLETE_CB_ID, adc_callback);
}

void Battery_ADC::start(){
//	HAL_ADC_Start(this->config.hadc);
//	HAL_ADC_Start_IT(this->config.hadc);
}
void Battery_ADC::startConversion() {
	HAL_ADC_Start_IT(this->config.hadc);
}



void adc_callback(ADC_HandleTypeDef* hadc) {
	if (hadc->Instance == ADC1) {
		uint32_t adc_value = HAL_ADC_GetValue(hadc);
		float voltage = ((float) adc_value) / 4095.0f * 3.3f * BATTERY_ADC_VOLTAGE_DIVIDER;
		battery_adc_instance->battery_voltage = voltage;
	}
}
