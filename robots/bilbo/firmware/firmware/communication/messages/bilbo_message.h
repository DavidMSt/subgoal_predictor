/*
 * bilbo_messages.h
 *
 *  Created on: 3 Mar 2023
 *      Author: lehmann_workstation
 */

#ifndef COMMUNICATION_BILBO_MESSAGES_H_
#define COMMUNICATION_BILBO_MESSAGES_H_

#include "core.h"
#include "bilbo_uart_communication.h"

//
//
//
//class BILBO_Message_t {
//public:
//
//	BILBO_Message_t(){
//
//	}
//
//	virtual core_comm_SerialMessage encode () = 0;
//
//
//private:
//
//};
//
//template<typename data_type_t, serial_message_type_t msg_type, uint8_t message_id>
//class BILBO_Message: public BILBO_Message_t {
//public:
//
//	BILBO_Message() {
//		this->data = &this->data_union.data;
//	}
//
//	BILBO_Message(data_type_t message_data) {
//		this->data = &this->data_union.data;
//		this->data_union.data = message_data;
//	}
//
//	core_comm_SerialMessage encode() override {
//		core_comm_SerialMessage msg;
//
//		msg.cmd = this->type;
//		msg.address_1 = 0x01;
//		msg.address_2 = this->id >> 8;
//		msg.address_3 = this->id;
//		msg.flag = 0x00;
//		msg.data_ptr = this->data_union.data_buffer;
//		msg.len = this->len;
//		return msg;
//	}
//
//	data_type_t decode(uint8_t* data) {
//		for (int i=0; i<this->len ; i++){
//			this->data_union.data_buffer[i] = data[i];
//		}
//		return this->data_union.data;
//	}
//
//
//	uint16_t len = sizeof(data_type_t);
//	serial_message_type_t type = msg_type;
//	uint8_t id = message_id;
//
//	union data_union_t {
//		uint8_t data_buffer[sizeof(data_type_t)];
//		data_type_t data;
//	} data_union;
//
//	data_type_t* data;
//
//private:
//
//};

#include <cstdint>
#include <cstring>
#include <type_traits>

class BILBO_Message_t {
public:
	virtual ~BILBO_Message_t() = default;
	virtual core_comm_SerialMessage encode() = 0;
};

template<typename data_type_t, serial_message_type_t msg_type,
		uint8_t message_id>
class BILBO_Message: public BILBO_Message_t {
public:
	static_assert(std::is_trivially_copyable_v<data_type_t>,
			"BILBO_Message payload must be trivially copyable (wire-safe).");

	BILBO_Message() {
		// zero-init buffer (optional; keeps deterministic bytes)
		std::memset(_buffer, 0, sizeof(_buffer));
	}

	explicit BILBO_Message(const data_type_t &message_data) {
		set(message_data);
	}

	// Set/replace payload
	void set(const data_type_t &v) {
		std::memcpy(_buffer, &v, sizeof(data_type_t));
	}

	// Get payload as a value (copy out)
	data_type_t get() const {
		data_type_t out;
		std::memcpy(&out, _buffer, sizeof(data_type_t));
		return out;
	}

	core_comm_SerialMessage encode() override {
		core_comm_SerialMessage msg;
		msg.cmd = type;
		msg.address_1 = 0x01;
		msg.address_2 = 0x00;         // id is uint8_t, so high byte is always 0
		msg.address_3 = id;
		msg.flag = 0x00;
		msg.data_ptr = _buffer;
		msg.len = len;
		return msg;
	}

	data_type_t get_mut_copy() const { return get(); }
	void set_from_copy(const data_type_t& v) { set(v); }

	// Fill from received bytes and return decoded value
	data_type_t decode(const uint8_t *data) {
		std::memcpy(_buffer, data, sizeof(data_type_t));
		return get();
	}

public:
	static constexpr uint16_t len = sizeof(data_type_t);
	static constexpr serial_message_type_t type = msg_type;
	static constexpr uint8_t id = message_id;

private:alignas(max_align_t) uint8_t _buffer[sizeof(data_type_t)];
};

#endif /* COMMUNICATION_BILBO_MESSAGES_H_ */
