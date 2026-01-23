/*
 * firmware_config.h
 *
 *  Created on: Jul 10, 2022
 *      Author: Dustin Lehmann
 */

#ifndef FIRMWARE_CONFIG_H_
#define FIRMWARE_CONFIG_H_

#include "stm32l4xx_hal.h"

extern I2C_HandleTypeDef hi2c1;
extern I2C_HandleTypeDef hi2c2;
extern TIM_HandleTypeDef htim1;
extern TIM_HandleTypeDef htim2;
extern TIM_HandleTypeDef htim15;


extern I2C_HandleTypeDef hi2c1;
extern I2C_HandleTypeDef hi2c2;

extern ADC_HandleTypeDef hadc1;

#define FIRMWARE_NEOPIXEL_INTERN_TIM &htim2
#define FIRMWARE_NEOPIXEL_INTERN_CHANNEL TIM_CHANNEL_1
#define FIRMWARE_NEOPIXEL_EXTERN_TIM &htim1
#define FIRMWARE_NEOPIXEL_EXTERN_CHANNEL TIM_CHANNEL_1
#define FIRMWARE_PWM_BUZZER_TIM &htim15
#define FIRMWARE_PWM_BUZZER_CHANNEL TIM_CHANNEL_1


#define FIRMWARE_I2C_INTERN &hi2c1

#define FIRMWARE_ADC &hadc1

#define BOARD_EEPROM_CONFIG_ADDRESS 0xA0

#endif /* FIRMWARE_CONFIG_H_ */
