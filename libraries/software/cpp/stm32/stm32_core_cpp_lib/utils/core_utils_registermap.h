/*
 * core_utils_registermap.h
 *
 *  Created on: 26 Feb 2023
 *      Author: Dustin Lehmann
 */

#ifndef UTILS_CORE_UTILS_REGISTERMAP_H_
#define UTILS_CORE_UTILS_REGISTERMAP_H_

template<typename T, typename U>
struct is_same {
	static const bool value = false;
};

template<typename T>
struct is_same<T, T> {
	static const bool value = true;
};

typedef enum register_entry_type_t {
	REGISTER_ENTRY_TYPE_NONE = 0,
	REGISTER_ENTRY_TYPE_EXECUTABLE = 1,
	REGISTER_ENTRY_TYPE_WRITABLE = 2,
	REGISTER_ENTRY_TYPE_READABLE = 3,
	REGISTER_ENTRY_TYPE_READWRITEABLE = 4
} register_entry_type_t;

/* ============================================================ */
class RegisterEntry {
public:
	virtual uint16_t getInputSize() {
		return 0;
	}

	virtual uint16_t getOutputSize() {
		return 0;
	}

	virtual void execute() {

	}

	virtual uint16_t execute(uint8_t *input, uint8_t *output) {
		return 0;
	}

	virtual void write(uint8_t *input) {

	}

	virtual uint16_t read(uint8_t *output) {
		return 0;
	}

	virtual register_entry_type_t getType() {
		return REGISTER_ENTRY_TYPE_NONE;
	}

	register_entry_type_t type;
};

/* ============================================================ */
class RegisterMap {
public:
	virtual void addEntry(uint8_t address, RegisterEntry *entry) {

	}
	virtual bool hasEntry(uint8_t address) {
		return false;
	}
	/* -------------------------------------------------- */
	virtual uint16_t getInputSize(uint8_t address) {
		return this->entries[address].getInputSize();
	}
	/* -------------------------------------------------- */
	virtual uint16_t getOutputSize(uint8_t address) {
		return this->entries[address].getOutputSize();
	}
	virtual register_entry_type_t getType(uint8_t address) {
		return REGISTER_ENTRY_TYPE_NONE;
	}
	/* -------------------------------------------------- */
	virtual uint16_t execute(uint8_t address, uint8_t *input, uint8_t *output) {
		return 0;
	}
	/* -------------------------------------------------- */
	virtual void write(uint8_t address, uint8_t *input) {

	}
	/* -------------------------------------------------- */
	virtual uint16_t read(uint8_t address, uint8_t *output) {
		return 0;
	}

	uint16_t address;
	RegisterEntry *entries;
};

/* ============================================================ */
template<int size>
class core_utils_RegisterMap: public RegisterMap {
public:
	core_utils_RegisterMap(uint8_t address) {
		this->address = address;
	}
	/* -------------------------------------------------- */
	uint16_t execute(uint8_t address, uint8_t *input, uint8_t *output) {
		if (this->entries[address] != NULL) {
			return this->entries[address]->execute(input, output);
		}
		return 0;
	}
	/* -------------------------------------------------- */
	void write(uint8_t address, uint8_t *input) {
		if (this->hasEntry(address)) {
			this->entries[address]->write(input);
		}
	}
	/* -------------------------------------------------- */
	uint16_t read(uint8_t address, uint8_t *output) {
		if (this->hasEntry(address)) {
			return this->entries[address]->read(output);
		}
		return 0;
	}
	/* -------------------------------------------------- */
	void addEntry(uint8_t address, RegisterEntry *entry) {
//		assert(this->entries[address] == nullptr && "Entry at this address is not NULL");
		this->entries[address] = entry;
	}
	/* -------------------------------------------------- */
	bool hasEntry(uint8_t address) {
		if (this->entries[address] != NULL) {
			return true;
		} else {
			return false;
		}
	}
	/* -------------------------------------------------- */
	uint16_t getInputSize(uint8_t address) {
		return this->entries[address]->getInputSize();
	}
	/* -------------------------------------------------- */
	uint16_t getOutputSize(uint8_t address) {
		return this->entries[address]->getOutputSize();
	}
	/* -------------------------------------------------- */

	register_entry_type_t getType(uint8_t address) {
		if (this->hasEntry(address)) {
			return this->entries[address]->getType();
		}
		return REGISTER_ENTRY_TYPE_NONE;
	}
	/* -------------------------------------------------- */
	RegisterEntry *entries[size] = { 0 };

};

/* ============================================================================================================================================= */
/* ============================================================================================================================================= */
/* ============================================================================================================================================= */
/* ============================================================================================================================================= */
/* ============================================================================================================================================= */
template<typename output_type, typename input_type>
class core_utils_RegisterEntry: public RegisterEntry {
public:

	/* --------------------------------------------------------------------------------------------------------- */
	core_utils_RegisterEntry(RegisterMap *map, uint8_t address,
			output_type (*function)(input_type)) {
		this->address = address;
		map->addEntry(this->address, this);
		this->callback = core_utils_Callback<output_type, input_type>(function);
		this->type = REGISTER_ENTRY_TYPE_EXECUTABLE;
	}

	/* --------------------------------------------------------------------------------------------------------- */
	core_utils_RegisterEntry(RegisterMap *map, uint8_t address,
			input_type *data) {
		static_assert(is_same<input_type, output_type>::value, "Types are not the same!");
		// Bit of a hack. READWRITABLE params need same input and output type
		this->address = address;
		map->addEntry(this->address, this);
		this->data = data;
		this->type = REGISTER_ENTRY_TYPE_READWRITEABLE;
	}

	/* --------------------------------------------------------------------------------------------------------- */
	template<typename cls>
	core_utils_RegisterEntry(RegisterMap *map, uint8_t address, cls *object,
			output_type (cls::*member)(input_type)) {
		this->address = address;
		map->addEntry(this->address, this);
		this->callback = core_utils_Callback<output_type, input_type>(object,
				member);
		this->type = REGISTER_ENTRY_TYPE_EXECUTABLE;
	}
	/* --------------------------------------------------------------------------------------------------------- */

	void execute(input_type input, output_type &output) {
		this->callback.call(input, output);
	}

	/* --------------------------------------------------------------------------------------------------------- */
	void execute(uint8_t *input_buffer, output_type &output) {
		for (uint8_t i = 0; i < sizeof(input_type); i++) {
			this->input_data_bytes[i] = input_buffer[i];
		}
		this->callback.call(*reinterpret_cast<input_type*>(this->input_data_bytes), output);
	}

	/* --------------------------------------------------------------------------------------------------------- */
	uint16_t execute(uint8_t *input_buffer, uint8_t *output_buffer) {
		for (uint8_t i = 0; i < sizeof(input_type); i++) {
			this->input_data_bytes[i] = input_buffer[i];
		}
		this->callback.call(*reinterpret_cast<input_type*>(this->input_data_bytes),
				*reinterpret_cast<output_type*>(this->output_data_bytes));
		for (uint8_t i = 0; i < sizeof(output_type); i++) {
			output_buffer[i] = this->output_data_bytes[i];
		}
		return this->getOutputSize();
	}
	/* --------------------------------------------------------------------------------------------------------- */
	void write(uint8_t *input) {
		if (this->type == REGISTER_ENTRY_TYPE_READWRITEABLE) {
			uint8_t *target_address = reinterpret_cast<uint8_t*>(this->data);
			for (uint8_t i = 0; i < sizeof(input_type); i++) {
				target_address[i] = input[i];
			}
		}
	}
	/* --------------------------------------------------------------------------------------------------------- */
	uint16_t read(uint8_t *output) {
		if (this->type == REGISTER_ENTRY_TYPE_READWRITEABLE) {
			uint8_t *target_address = reinterpret_cast<uint8_t*>(this->data);
			for (uint8_t i = 0; i < sizeof(output_type); i++) {
				output[i] = target_address[i];
			}
			return sizeof(output_type);
		}
		return 0;
	}

	/* --------------------------------------------------------------------------------------------------------- */
	uint16_t getInputSize() {
		return sizeof(input_type);
	}

	/* --------------------------------------------------------------------------------------------------------- */
	uint16_t getOutputSize() {
		return sizeof(output_type);
	}
	/* --------------------------------------------------------------------------------------------------------- */
	register_entry_type_t getType() {
		return this->type;
	}

	alignas(input_type) uint8_t input_data_bytes[sizeof(input_type)];
	alignas(output_type) uint8_t output_data_bytes[sizeof(output_type)];

	input_type *data = NULL;
	uint8_t address;
	register_entry_type_t type;
	core_utils_Callback<output_type, input_type> callback;

};

/* ============================================================================================================================================= */
template<typename input_type>
class core_utils_RegisterEntry<void, input_type> : public RegisterEntry {
public:

	/* --------------------------------------------------------------------------------------------------------- */
	core_utils_RegisterEntry(RegisterMap *map, uint8_t address,
			void (*function)(input_type)) {
		this->address = address;
		map->addEntry(this->address, this);
		this->callback = core_utils_Callback<void, input_type>(function);
		this->type = REGISTER_ENTRY_TYPE_EXECUTABLE;
	}
	/* --------------------------------------------------------------------------------------------------------- */
	core_utils_RegisterEntry(RegisterMap *map, uint8_t address,
			input_type *data) {
		this->address = address;
		map->addEntry(this->address, this);
		this->type = REGISTER_ENTRY_TYPE_WRITABLE;
		this->data = data;
//			this->callback = core_utils_Callback<void, input_type>(function);
	}
	/* --------------------------------------------------------------------------------------------------------- */
	template<typename cls>
	core_utils_RegisterEntry(RegisterMap *map, uint8_t address, cls *object,
			void (cls::*member)(input_type)) {
		this->address = address;
		map->addEntry(this->address, this);
		this->callback = core_utils_Callback<void, input_type>(object, member);
		this->type = REGISTER_ENTRY_TYPE_EXECUTABLE;
	}
	/* --------------------------------------------------------------------------------------------------------- */

	void execute(input_type input) {
		this->callback.call(input);
	}

	/* --------------------------------------------------------------------------------------------------------- */
	void execute(uint8_t *input_buffer) {
		for (uint8_t i = 0; i < sizeof(input_type); i++) {
			this->input_data_bytes[i] = input_buffer[i];
		}
		this->callback.call(*reinterpret_cast<input_type*>(this->input_data_bytes));
	}

	/* --------------------------------------------------------------------------------------------------------- */
	uint16_t execute(uint8_t *input_buffer, uint8_t *output_buffer) {
		for (uint8_t i = 0; i < sizeof(input_type); i++) {
			this->input_data_bytes[i] = input_buffer[i];
		}
		this->callback.call(*reinterpret_cast<input_type*>(this->input_data_bytes));
		return this->getOutputSize();
	}
	/* --------------------------------------------------------------------------------------------------------- */
	void write(uint8_t *input) {
		if (this->type == REGISTER_ENTRY_TYPE_WRITABLE) {
			uint8_t *target_address = reinterpret_cast<uint8_t*>(this->data);
			for (uint8_t i = 0; i < sizeof(input_type); i++) {
				target_address[i] = input[i];
			}
		}
	}
	/* --------------------------------------------------------------------------------------------------------- */
	uint16_t getInputSize() {
		return sizeof(input_type);
	}

	/* --------------------------------------------------------------------------------------------------------- */
	uint16_t getOutputSize() {
		return 0;
	}
	/* --------------------------------------------------------------------------------------------------------- */
	register_entry_type_t getType() {
		return this->type;
	}
	/* --------------------------------------------------------------------------------------------------------- */

	alignas(input_type) uint8_t input_data_bytes[sizeof(input_type)];

	input_type *data = NULL;
	uint8_t address;
	register_entry_type_t type;
	core_utils_Callback<void, input_type> callback;

};

/* ============================================================================================================================================= */
template<typename output_type>
class core_utils_RegisterEntry<output_type, void> : public RegisterEntry {
public:

	/* --------------------------------------------------------------------------------------------------------- */
	core_utils_RegisterEntry(RegisterMap *map, uint8_t address,
			output_type (*function)(void)) {
		this->address = address;
		map->addEntry(this->address, this);
		this->callback = core_utils_Callback<output_type, void>(function);
		this->type = REGISTER_ENTRY_TYPE_EXECUTABLE;
	}

	/* --------------------------------------------------------------------------------------------------------- */
	core_utils_RegisterEntry(RegisterMap *map, uint8_t address,
			output_type *data) {
		this->address = address;
		map->addEntry(this->address, this);
//		this->callback = core_utils_Callback<output_type, void>(function);
		this->data = data;
		this->type = REGISTER_ENTRY_TYPE_READABLE;
	}

	/* --------------------------------------------------------------------------------------------------------- */
	template<typename cls>
	core_utils_RegisterEntry(RegisterMap *map, uint8_t address, cls *object,
			output_type (cls::*member)(void)) {
		this->address = address;
		map->addEntry(this->address, this);
		this->callback = core_utils_Callback<output_type, void>(object, member);
		this->type = REGISTER_ENTRY_TYPE_EXECUTABLE;
	}
	/* --------------------------------------------------------------------------------------------------------- */

	void execute(output_type &output) {
		this->callback.call(output);
	}

	/* --------------------------------------------------------------------------------------------------------- */
	uint16_t execute(uint8_t *input_buffer, uint8_t *output_buffer) {
		this->callback.call(*reinterpret_cast<output_type*>(this->output_data_bytes));
		for (uint8_t i = 0; i < sizeof(output_type); i++) {
			output_buffer[i] = this->output_data_bytes[i];
		}
		return this->getOutputSize();
	}
	/* --------------------------------------------------------------------------------------------------------- */
	uint16_t read(uint8_t *output) {
		if (this->type == REGISTER_ENTRY_TYPE_READABLE) {
			uint8_t *target_address = reinterpret_cast<uint8_t*>(this->data);
			for (uint8_t i = 0; i < sizeof(output_type); i++) {
				output[i] = target_address[i];
			}
			return sizeof(output_type);
		}
		return 0;
	}

	/* --------------------------------------------------------------------------------------------------------- */
	uint16_t getInputSize() {
		return 0;
	}

	/* --------------------------------------------------------------------------------------------------------- */
	uint16_t getOutputSize() {
		return sizeof(output_type);
	}
	/* --------------------------------------------------------------------------------------------------------- */
	register_entry_type_t getType() {
		return this->type;
	}
	/* --------------------------------------------------------------------------------------------------------- */

	alignas(output_type) uint8_t output_data_bytes[sizeof(output_type)];

	output_type *data;
	uint8_t address;
	register_entry_type_t type;
	core_utils_Callback<output_type, void> callback;

};

/* ============================================================================================================================================= */
template<>
class core_utils_RegisterEntry<void, void> : public RegisterEntry {
public:

	/* --------------------------------------------------------------------------------------------------------- */
	core_utils_RegisterEntry(RegisterMap *map, uint8_t address,
			void (*function)(void)) {
		this->address = address;
		map->addEntry(this->address, this);
		this->callback = core_utils_Callback<void, void>(function);
		this->type = REGISTER_ENTRY_TYPE_EXECUTABLE;
	}

	/* --------------------------------------------------------------------------------------------------------- */
	template<typename cls>
	core_utils_RegisterEntry(RegisterMap *map, uint8_t address, cls *object,
			void (cls::*member)(void)) {
		this->address = address;
		map->addEntry(this->address, this);
		this->callback = core_utils_Callback<void, void>(object, member);
		this->type = REGISTER_ENTRY_TYPE_EXECUTABLE;
	}
	/* --------------------------------------------------------------------------------------------------------- */
	void execute() {
		this->callback.call();
	}
	/* --------------------------------------------------------------------------------------------------------- */
	uint16_t execute(uint8_t *input_buffer, uint8_t *output_buffer) {
		this->callback.call();
		return this->getOutputSize();
	}
	/* --------------------------------------------------------------------------------------------------------- */
	uint16_t getInputSize() {
		return 0;
	}

	/* --------------------------------------------------------------------------------------------------------- */
	uint16_t getOutputSize() {
		return 0;
	}
	/* --------------------------------------------------------------------------------------------------------- */
	register_entry_type_t getType() {
		return this->type;
	}
	/* --------------------------------------------------------------------------------------------------------- */

	uint8_t address;
	register_entry_type_t type;
	core_utils_Callback<void, void> callback;

};

#endif /* UTILS_CORE_UTILS_REGISTERMAP_H_ */
