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
I2C_Slave::I2C_Slave() {

}

void I2C_Slave::init(i2c_slave_config_t config) {
	this->config = config;
	this->hi2c = this->config.hi2c;
	this->address = this->config.address;
	this->register_map = this->config.registerMap;
	this->register_map_length = this->config.num_registers;

	registered_i2c_slaves[num_i2c_slave] = this;
	num_i2c_slave++;
}

void I2C_Slave::start() {
	HAL_I2C_EnableListen_IT(this->hi2c);
}

void I2C_Slave::i2c_addrCallback(uint8_t TransferDirection,
		uint16_t AddrMatchCode) {

	if (TransferDirection == I2C_DIRECTION_TRANSMIT) {
		this->direction = I2C_SLAVE_DIRECTION_TRANSMIT;
		if (this->_received_bytes == 0) {
			HAL_I2C_Slave_Seq_Receive_IT(this->hi2c, &this->bufferAddress, 1,
			I2C_NEXT_FRAME);
		} else {
		}

	} else if (TransferDirection == I2C_DIRECTION_RECEIVE) {
		this->direction = I2C_SLAVE_DIRECTION_RECEIVE;
		HAL_I2C_Slave_Seq_Transmit_IT(this->hi2c,
				&this->register_map[this->bufferAddress], 1, I2C_NEXT_FRAME);
	}
}
void I2C_Slave::i2c_listenCompleteCallback() {

	uint8_t startAddress = this->bufferAddress - this->_received_bytes;
	this->lastReceivedBytes = this->_received_bytes;

	this->_received_bytes = 0;
	this->_sent_bytes = 0;
	HAL_I2C_EnableListen_IT(this->hi2c);

	if (this->callbacks.listen_cmplt_callback.registered) {
		this->callbacks.listen_cmplt_callback.call(startAddress);
	}
}

void I2C_Slave::i2c_rxCompleteCallback() {
	this->_received_bytes++;
	if (this->_received_bytes > 1) {
		this->bufferAddress++;
	}
	HAL_I2C_Slave_Seq_Receive_IT(this->hi2c,
			&this->register_map[this->bufferAddress], 1, I2C_NEXT_FRAME);
}
void I2C_Slave::i2c_txCompleteCallback() {
	this->bufferAddress++;
	this->_sent_bytes++;
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
