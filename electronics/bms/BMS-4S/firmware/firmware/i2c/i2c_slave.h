/*
 * i2c_slave.h
 *
 *  Created on: Jul 11, 2022
 *      Author: Dustin Lehmann
 */

#ifndef I2C_I2C_SLAVE_H_
#define I2C_I2C_SLAVE_H_

#include "stm32l4xx_hal.h"
#include "stm32l4xx_hal_i2c.h"
#include "core_utils_Callback.h"

#define FIRMWARE_NUM_I2C_SLAVES 1

enum I2C_Slave_mode {
	I2C_SLAVE_MODE_IT
};

enum I2C_Slave_direction {
	I2C_SLAVE_DIRECTION_TRANSMIT, I2C_SLAVE_DIRECTION_RECEIVE
};

enum I2C_Slave_callback_id {
	I2C_SLAVE_CB_LISTEN_CMPLT
};

struct I2C_Slave_callbacks {
	core_utils_Callback<void, uint8_t> listen_cmplt_callback;
};


typedef struct i2c_slave_config_t{
	I2C_HandleTypeDef* hi2c;
	I2C_Slave_mode mode;
	uint8_t address;
	uint8_t *registerMap;
	uint8_t num_registers;
} i2c_slave_config_t;

class I2C_Slave {
public:

	I2C_Slave();

	void init(i2c_slave_config_t config);
	void start();

	void i2c_addrCallback(uint8_t TransferDirection, uint16_t AddrMatchCode);
	void i2c_listenCompleteCallback();
	void i2c_rxCompleteCallback();
	void i2c_txCompleteCallback();
	void i2c_errorCallback();
	void i2c_abortCompleteCallback();

	i2c_slave_config_t config;

	I2C_Slave_callbacks callbacks;
	I2C_HandleTypeDef *hi2c;
	uint8_t *register_map = NULL;
	uint8_t bufferAddress = 0;
	uint8_t register_map_length;
	I2C_Slave_direction direction;

	uint8_t lastReceivedBytes=0;


private:
	uint8_t address;
	uint8_t _received_bytes = 0;
	uint8_t _sent_bytes = 0;
};

I2C_Slave* get_I2C_slave(I2C_HandleTypeDef *hi2c);

#endif /* I2C_I2C_SLAVE_H_ */
