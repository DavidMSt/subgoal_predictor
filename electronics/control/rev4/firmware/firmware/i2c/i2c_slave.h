/*
 * i2c_slave.h
 *
 *  Created on: Jul 11, 2022
 *      Author: Dustin Lehmann
 */

#ifndef I2C_I2C_SLAVE_H_
#define I2C_I2C_SLAVE_H_

#include "stm32l4xx_hal.h"
#include "callback.h"

#define FIRMWARE_NUM_I2C_SLAVES 2

enum I2C_Slave_mode {
	I2C_SLAVE_MODE_IT
};

enum I2C_Slave_direction {
	I2C_SLAVE_DIRECTION_TRANSMIT, I2C_SLAVE_DIRECTION_RECEIVE
};

enum I2C_Slave_callback_id {
	I2C_SLAVE_CB_LISTEN_CMPLT
};

typedef struct I2C_Slave_config {
	I2C_Slave_mode mode;
} I2C_Slave_config;

struct I2C_Slave_callbacks {
	core_utils_Callback listen_cmplt_callback;
};

class I2C_Slave {
public:

	I2C_Slave(I2C_HandleTypeDef *hi2c, uint8_t address, uint8_t *registerMap, uint8_t num_registers);
	I2C_Slave(I2C_HandleTypeDef *hi2c, uint8_t address,
			I2C_Slave_config config, uint8_t *registerMap, uint8_t num_registers);

	void init();
	void start();

	void i2c_addrCallback(uint8_t TransferDirection, uint16_t AddrMatchCode);
	void i2c_listenCompleteCallback();
	void i2c_rxCompleteCallback();
	void i2c_txCompleteCallback();
	void i2c_errorCallback();
	void i2c_abortCompleteCallback();

	void registerCallback(I2C_Slave_callback_id callback_id,
			void (*callback)(void *argument, void *params), void *params);

	I2C_Slave_callbacks callbacks;
	I2C_Slave_config config;
	I2C_HandleTypeDef *hi2c;
	uint8_t *register_map = NULL;
	uint8_t bufferAddress = 0;
	uint8_t register_map_length;
	I2C_Slave_direction direction;

	uint8_t received_bytes = 0;
	uint8_t sent_bytes = 0;
private:
	uint8_t address;
};

I2C_Slave* get_I2C_slave(I2C_HandleTypeDef *hi2c);

#endif /* I2C_I2C_SLAVE_H_ */
