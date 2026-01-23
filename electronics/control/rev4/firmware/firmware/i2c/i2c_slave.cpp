/*
 * i2c_slave.cpp
 *
 *  Created on: Jul 11, 2022
 *      Author: Dustin Lehmann
 */

#include "i2c_slave.h"

I2C_Slave *registered_i2c_slaves[FIRMWARE_NUM_I2C_SLAVES];
uint8_t num_i2c_slave = 0;

void nop() {

}

I2C_Slave* get_I2C_slave(I2C_HandleTypeDef *hi2c) {
	for (int i = 0; i < num_i2c_slave; i++) {
		if (registered_i2c_slaves[i]->hi2c == hi2c) {
			return registered_i2c_slaves[i];
		}
	}
	return NULL;
}

void HAL_I2C_ListenCpltCallback(I2C_HandleTypeDef *hi2c) {
	I2C_Slave *slave = get_I2C_slave(hi2c);
	if (slave != NULL) {
		slave->i2c_listenCompleteCallback();
	}
}

void HAL_I2C_AddrCallback(I2C_HandleTypeDef *hi2c, uint8_t TransferDirection,
		uint16_t AddrMatchCode) {
	I2C_Slave *slave = get_I2C_slave(hi2c);
	if (slave != NULL) {
		slave->i2c_addrCallback(TransferDirection, AddrMatchCode);
	}
}

void HAL_I2C_SlaveRxCpltCallback(I2C_HandleTypeDef *hi2c) {
	I2C_Slave *slave = get_I2C_slave(hi2c);
	if (slave != NULL) {
		slave->i2c_rxCompleteCallback();
	}
}

void HAL_I2C_SlaveTxCpltCallback(I2C_HandleTypeDef *hi2c) {
	I2C_Slave *slave = get_I2C_slave(hi2c);
	if (slave != NULL) {
		slave->i2c_txCompleteCallback();
	}
}

void HAL_I2C_ErrorCallback(I2C_HandleTypeDef *hi2c) {
	I2C_Slave *slave = get_I2C_slave(hi2c);
	uint32_t x = HAL_I2C_GetError(hi2c);
	if (slave != NULL) {
		slave->i2c_errorCallback();
	}
}

void HAL_I2C_AbortCpltCallback(I2C_HandleTypeDef *hi2c) {
	I2C_Slave *slave = get_I2C_slave(hi2c);
	if (slave != NULL) {
		slave->i2c_abortCompleteCallback();
	}
}

/* ===================================================================== */
I2C_Slave::I2C_Slave(I2C_HandleTypeDef *hi2c, uint8_t address,
		uint8_t *registerMap, uint8_t num_registers) {
	this->hi2c = hi2c;
	this->address = address;
	this->register_map = registerMap;
	this->register_map_length = num_registers;

	registered_i2c_slaves[num_i2c_slave] = this;
	num_i2c_slave++;
}

I2C_Slave::I2C_Slave(I2C_HandleTypeDef *hi2c, uint8_t address,
		I2C_Slave_config config, uint8_t *registerMap, uint8_t num_registers) {
	this->hi2c = hi2c;
	this->address = address;
	this->config = config;
	this->register_map = registerMap;
	this->register_map_length = num_registers;

	registered_i2c_slaves[num_i2c_slave] = this;
	num_i2c_slave++;
}

void I2C_Slave::init() {

}

void I2C_Slave::start() {
	HAL_I2C_EnableListen_IT(this->hi2c);
}

void I2C_Slave::registerCallback(I2C_Slave_callback_id callback_id,
		void (*callback)(void *argument, void *params), void *params) {
	switch (callback_id) {
	case I2C_SLAVE_CB_LISTEN_CMPLT: {
		this->callbacks.listen_cmplt_callback.callback = callback;
		this->callbacks.listen_cmplt_callback.params = params;
		this->callbacks.listen_cmplt_callback.registered = 1;
		break;
	}
	}
}

void I2C_Slave::i2c_addrCallback(uint8_t TransferDirection,
		uint16_t AddrMatchCode) {

	if (TransferDirection == I2C_DIRECTION_TRANSMIT) {
		this->direction = I2C_SLAVE_DIRECTION_TRANSMIT;
		if (this->received_bytes == 0) {
			HAL_StatusTypeDef status = HAL_I2C_Slave_Seq_Receive_IT(this->hi2c, &this->bufferAddress, 1,
			I2C_NEXT_FRAME);
			nop();
		} else {
			nop();
		}

	} else if (TransferDirection == I2C_DIRECTION_RECEIVE) {
		this->direction = I2C_SLAVE_DIRECTION_RECEIVE;
		HAL_I2C_Slave_Seq_Transmit_IT(this->hi2c,
				&this->register_map[this->bufferAddress], 1, I2C_NEXT_FRAME);
	}
}
void I2C_Slave::i2c_listenCompleteCallback() {

	this->received_bytes = 0;
	this->sent_bytes = 0;
	HAL_I2C_EnableListen_IT(this->hi2c);
	if (this->callbacks.listen_cmplt_callback.registered) {
		this->callbacks.listen_cmplt_callback.call(this);
	}
}
void I2C_Slave::i2c_rxCompleteCallback() {
	this->received_bytes++;
	if (this->received_bytes > 1) {

		this->bufferAddress++;

	}
	HAL_I2C_Slave_Seq_Receive_IT(this->hi2c,
			&this->register_map[this->bufferAddress], 1, I2C_NEXT_FRAME);

}
void I2C_Slave::i2c_txCompleteCallback() {
	this->bufferAddress++;
	this->sent_bytes++;
	HAL_I2C_Slave_Seq_Transmit_IT(this->hi2c,
			&this->register_map[this->bufferAddress], 1, I2C_NEXT_FRAME);

}
void I2C_Slave::i2c_errorCallback() {
	nop();
	HAL_I2C_EnableListen_IT(this->hi2c);
}
void I2C_Slave::i2c_abortCompleteCallback() {
	nop();
}
