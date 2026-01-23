/*
 * firmware.h
 *
 *  Created on: Jan 4, 2025
 *      Author: lehmann
 */

#ifndef FIRMWARE_H_
#define FIRMWARE_H_

#include "i2c_slave.h"
#include "utils.h"
#include "elapsedMillis.h"
#include "adc.h"

extern I2C_HandleTypeDef hi2c1;
#define I2C_SLAVE_EXTERN hi2c1;

extern I2C_HandleTypeDef hi2c3;
#define I2C_MASTER_INTERN hi2c3;



#define CHG_DETECT_PORT DETECT_CHG_GPIO_Port
#define CHG_DETECT_PIN DETECT_CHG_Pin

#define OUT_1_PORT OUT_1_GPIO_Port
#define OUT_1_PIN OUT_1_Pin
#define OUT_2_PORT OUT_2_GPIO_Port
#define OUT_2_PIN OUT_2_Pin
#define OUT_3_PORT OUT_3_GPIO_Port
#define OUT_3_PIN OUT_3_Pin
#define OUT_4_PORT OUT_4_GPIO_Port
#define OUT_4_PIN OUT_4_Pin

#define USER_LED_PORT LED_USER_GPIO_Port
#define USER_LED_PIN LED_USER_Pin

#define ENABLE_MEAS_1_PORT GPIOB
#define ENABLE_MEAS_1_PIN GPIO_PIN_1
#define ENABLE_MEAS_2_PORT GPIOA
#define ENABLE_MEAS_2_PIN GPIO_PIN_5
#define ENABLE_MEAS_3_PORT GPIOA
#define ENABLE_MEAS_3_PIN GPIO_PIN_3
#define ENABLE_MEAS_4_PORT GPIOA
#define ENABLE_MEAS_4_PIN GPIO_PIN_1


#define CELL_1_ADC_CHANNEL ADC_CHANNEL_15
#define CELL_2_ADC_CHANNEL ADC_CHANNEL_9
#define CELL_3_ADC_CHANNEL ADC_CHANNEL_7
#define CELL_4_ADC_CHANNEL ADC_CHANNEL_5


// Register Map
#define REG_OUTPUT_1 0x01 // Motor 1 Output
#define REG_OUTPUT_2 0x02 // Motor 2 Output
#define REG_OUTPUT_3 0x03 // Motor 3 Output
#define REG_BAT_VOLTAGE 0x04 // 4 Bytes Battery Voltage
#define REG_CELL_1_VOLTAGE 0x08
#define REG_CELL_2_VOLTAGE 0x0C
#define REG_CELL_3_VOLTAGE 0x10
#define REG_CELL_4_VOLTAGE 0x14
#define REG_CURRENT 0x18

#define REG_SHUTDOWN 0xA0

#define REG_DEBUG_1 0xAA
#define REG_DEBUG_2 0xBB


class Firmware {
public:
	Firmware();
	void init();
	void start();

	void task();
	void update();

	void setOutputs(bool out1, bool out2, bool out3, bool out4);
	bool checkChargeState();

	float measureCell(uint8_t cell);



	float battery_voltage = 0.0;
	float cell_1_voltage = 0.0;
	float cell_2_voltage = 0.0;
	float cell_3_voltage = 0.0;
	float cell_4_voltage = 0.0;
	float current = 0.0;


	elapsedMillis updateTimer;

	uint8_t register_map[256] = { 0 };
	I2C_Slave i2c_slave;
	ADC adc;

	void i2c_slave_receive_callback(uint8_t address);


private:


};

#endif /* FIRMWARE_H_ */
