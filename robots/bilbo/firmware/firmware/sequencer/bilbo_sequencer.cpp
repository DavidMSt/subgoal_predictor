/*
 * bilbo_sequencer.cpp
 *
 *  Created on: Nov 22, 2025
 *      Author: lehmann
 */

/*
 * twipr_sequencer.cpp
 *
 *  Created on: Nov 20, 2024
 *      Author: Dustin Lehmann
 */

#include "bilbo_sequencer.h"
#include "twipr_communication.h"
#include "robot-control_std.h"

_RAM_D2 twipr_sequence_input_t rx_sequence_buffer[TWIPR_SEQUENCE_BUFFER_SIZE ];
_RAM_D2 twipr_sequence_input_t sequence_buffer[TWIPR_SEQUENCE_BUFFER_SIZE ];

// Global pointer used by C-style DMA callback.
BILBO_Sequencer *sequencer = nullptr;

/* =============================================================== */
BILBO_Sequencer::BILBO_Sequencer() :
		mode(TWIPR_SEQUENCER_MODE_IDLE), sequence_tick(0), config { }, loaded_sequence { }, _start_requested(
				false), _start_requested_id(0), _start_request_tick(0) {
}

/* =============================================================== */
void BILBO_Sequencer::init(twipr_sequencer_config_t cfg) {
	this->config = cfg;
	this->sequence_tick = 0;
	this->mode = TWIPR_SEQUENCER_MODE_IDLE;

	sequencer = this;

	this->resetSequenceData();

	// Register callbacks from communication and control layers
	this->config.comm->callbacks.trajectory_received.registerFunction(this,
			&BILBO_Sequencer::spiSequenceReceived_callback);

	this->config.control->callbacks.mode_change.registerFunction(this,
			&BILBO_Sequencer::modeChange_callback);

	// Register DMA completion callback for trajectory transfer
	HAL_DMA_RegisterCallback(
	TWIPR_FIRMWARE_TRAJECTORY_DMA_STREAM, HAL_DMA_XFER_CPLT_CB_ID,
			trajectory_dma_transfer_cmplt_callback);
}

/* =============================================================== */
void BILBO_Sequencer::start() {
	// Currently nothing to do here, kept for symmetry / future use.
}

/* =============================================================== */
void BILBO_Sequencer::update() {

	// ---------------------------------------------------------------------
	// 1) Handle delayed start on a 10 Hz grid (tick_global divisible by 10)
	// ---------------------------------------------------------------------
	if (this->mode == TWIPR_SEQUENCER_MODE_IDLE && this->_start_requested) {
		if ((tick_global % START_ALIGNMENT_TICKS) == 0U) {
			// Try to actually start. If it fails, internal function clears the flag.
			this->_startSequenceInternal();
		}
	}

	// ---------------------------------------------------------------------
	// 2) If not running after the potential start, nothing to do.
	// ---------------------------------------------------------------------
	if (this->mode != TWIPR_SEQUENCER_MODE_RUNNING) {
		return;
	}

	// ---------------------------------------------------------------------
	// 3) Sequencer is running. Do the regular update.
	// ---------------------------------------------------------------------

	// If this is the first sample in the sequence, send out the trajectory started message
	if (this->sequence_tick == 0) {
		sequencer_event_message_data_t event_message_data = { .event =
				TRAJECTORY_STARTED, .sequence_id =
				this->loaded_sequence.sequence_id, .sequence_tick = 0, .tick =
				tick_global };
		BILBO_Message_Sequencer_Event msg(event_message_data);
		sendMessage(msg);

		// Disable Theta Integral Control and Velocity Integral Control during the sequence
		this->config.control->set_tic_enabled(false);
		this->config.control->set_vic_enabled(false);
	}

	// Check if we have reached the end of the sequence
	if (this->sequence_tick >= this->loaded_sequence.length) {
		this->finishSequence();

		// Re-Enable VIC. TIC has to be manually enabled from the host
		this->config.control->set_vic_enabled(true);

		return;
	}

	// Get the input from the sequence
	twipr_sequence_input_t current_input = sequence_buffer[this->sequence_tick];

	// Apply the input to the controller depending on control mode.
	// Write _external_input directly (friend access) because the sequencer
	// disables the external-input gate to block joystick/UI during playback,
	// so the gated set_external_input() would silently drop these values.
	if (this->loaded_sequence.control_mode == bilbo_control_mode_t::BALANCING) {
		this->config.control->_external_input = { .u_left =
				current_input.u_1, .u_right = current_input.u_2 };
	}


	this->sequence_tick++;
}

/* =============================================================== */
bool BILBO_Sequencer::startSequence(uint16_t id) {
	// This function only validates and queues a start request.
	// The actual start is aligned and executed in update().

	this->sequence_tick = 0;

	// Do not allow new starts while running
	if (this->mode == TWIPR_SEQUENCER_MODE_RUNNING) {
		send_error(
				"Sequence %d is currently running. Cannot start a new sequence",
				this->loaded_sequence.sequence_id);
		return false;
	}

	// Check that we have meta data and data loaded
	if (!this->loaded_sequence.loaded) {
		send_error("Cannot start sequence %d. Not received", id);
		return false;
	}

	// Check the sequence id
	if (this->loaded_sequence.sequence_id != id) {
		send_error("Cannot start sequence %d. Other sequence loaded: %d", id,
				this->loaded_sequence.sequence_id);
		return false;
	}

	// Check the control mode requirement already here (fast feedback)
	if (this->config.control->mode != this->loaded_sequence.control_mode) {
		send_error(
				"Cannot start sequence %d. Wrong control mode: %d (Required: %d)",
				id, this->config.control->mode,
				this->loaded_sequence.control_mode);
		return false;
	}

	// Queue start request
	this->_start_requested = true;
	this->_start_requested_id = id;
	this->_start_request_tick = tick_global;

	send_debug(
			"Queued start of sequence %d at tick %lu (will start on 10 Hz grid)",
			id, (unsigned long) tick_global);

	return true;
}

/* =============================================================== */
bool BILBO_Sequencer::_startSequenceInternal() {
	// Called from update() when we are aligned to the grid

	if (!this->_start_requested) {
		// Nothing to do
		return false;
	}

	// Re-check that sequence is still valid and loaded
	if (!this->loaded_sequence.loaded) {
		send_error("Cannot start sequence %d. Sequence data not loaded",
				this->_start_requested_id);
		this->_start_requested = false;
		this->_sendStartFailedAbort();
		return false;
	}

	// Re-check the requested id still matches the loaded sequence
	if (this->loaded_sequence.sequence_id != this->_start_requested_id) {
		send_error("Cannot start sequence %d. Other sequence loaded: %d",
				this->_start_requested_id, this->loaded_sequence.sequence_id);
		this->_start_requested = false;
		this->_sendStartFailedAbort();
		return false;
	}

	// Re-check control mode (it might have changed after the request)
	if (this->config.control->mode != this->loaded_sequence.control_mode) {
		send_error(
				"Cannot start sequence %d. Wrong control mode: %d (Required: %d)",
				this->loaded_sequence.sequence_id, this->config.control->mode,
				this->loaded_sequence.control_mode);
		this->_start_requested = false;
		this->_sendStartFailedAbort();
		return false;
	}

	this->sequence_tick = 0;
	this->mode = TWIPR_SEQUENCER_MODE_RUNNING;

	// Disable External Inputs to the controller
	this->config.control->disable_external_input();

	send_info("Start Sequence %d with length %d (aligned start at tick %lu)",
			this->loaded_sequence.sequence_id, this->loaded_sequence.length,
			(unsigned long) tick_global);

	// Call the callback(s)
	if (this->_callbacks.started.registered) {
		this->_callbacks.started.call(
				(uint16_t) this->loaded_sequence.sequence_id);
	}

	// Clear request
	this->_start_requested = false;

	return true;
}

/* =============================================================== */
void BILBO_Sequencer::abortSequence() {
	// TODO: reflect in the sample if the sequence was finished or aborted

	// Enable external inputs to the controller
	this->config.control->enable_external_input();

	this->config.control->reset_external_input();

	// Set the mode
	this->mode = TWIPR_SEQUENCER_MODE_ERROR;

	send_warning("Sequence %d has been aborted",
			this->loaded_sequence.sequence_id);

	sequencer_event_message_data_t event_message_data = { .event =
			TRAJECTORY_ABORTED,
			.sequence_id = this->loaded_sequence.sequence_id, .sequence_tick =
					this->sequence_tick, .tick = tick_global };
	BILBO_Message_Sequencer_Event msg(event_message_data);
	sendMessage(msg);

	if (this->_callbacks.aborted.registered) {
		this->_callbacks.aborted.call(
				(uint16_t) this->loaded_sequence.sequence_id);
	}

	// Re-enable VIC (TIC has to be manually re-enabled from the host)
	this->config.control->set_vic_enabled(true);

	// Clear any pending start requests
	this->_start_requested = false;
	this->_start_requested_id = 0;

	this->resetSequenceData();
}

/* =============================================================== */
void BILBO_Sequencer::finishSequence() {

	// Set the sequencer mode mode
	this->mode = TWIPR_SEQUENCER_MODE_IDLE;

	send_info("Sequence %d finished", this->loaded_sequence.sequence_id);

	sequencer_event_message_data_t event_message_data = { .event =
			TRAJECTORY_FINISHED, .sequence_id =
			this->loaded_sequence.sequence_id, .sequence_tick =
			this->sequence_tick, .tick = tick_global };
	BILBO_Message_Sequencer_Event msg(event_message_data);

	sendMessage(msg);

	if (this->_callbacks.finished.registered) {
		this->_callbacks.finished.call(
				(uint16_t) this->loaded_sequence.sequence_id);
	}

	// Set the control mode to the desired mode
	this->config.control->set_mode(this->loaded_sequence.control_mode_end);

	this->resetSequenceData();

	// Enable external inputs to the controller
	this->config.control->enable_external_input();

	// Set the controller inputs to zero
	this->config.control->reset_external_input();
}

/* =============================================================== */
bool BILBO_Sequencer::loadSequence(
		twipr_sequencer_sequence_data_t sequence_data) {

	send_debug("Load sequence %d with length %d", sequence_data.sequence_id,
			sequence_data.length);

	if (this->mode == TWIPR_SEQUENCER_MODE_RUNNING) {
		send_error("Sequence %d currently running. Cannot load new sequence",
				this->loaded_sequence.sequence_id);
		return false;
	}

	// Do not accept sequences with id=0
	if (sequence_data.sequence_id == 0) {
		send_error("Sequence needs an identifier != 0");
		return false;
	}

	if (sequence_data.length > TWIPR_SEQUENCE_BUFFER_SIZE) {
		send_error("Sequence %d too long: %d samples (%d max)",
				sequence_data.sequence_id, sequence_data.length,
				TWIPR_SEQUENCE_BUFFER_SIZE);
		return false;
	}

	// Check the required control mode. For now, we only accept balancing. TODO
	if (sequence_data.control_mode != bilbo_control_mode_t::BALANCING) {
		send_error("Sequence with control mode %d is not yet supported",
				sequence_data.control_mode);
		return false;
	}

	this->loaded_sequence = sequence_data;
	this->loaded_sequence.loaded = false;
	this->mode = TWIPR_SEQUENCER_MODE_IDLE;

	// Clear any pending start requests to avoid stale requests
	this->_start_requested = false;
	this->_start_requested_id = 0;

	return true;
}

/* =============================================================== */
twipr_sequencer_sequence_data_t BILBO_Sequencer::readSequence() {
	return this->loaded_sequence;
}

/* =============================================================== */
void BILBO_Sequencer::_sendStartFailedAbort() {
	sequencer_event_message_data_t event_message_data = { .event =
			TRAJECTORY_ABORTED,
			.sequence_id = this->loaded_sequence.sequence_id, .sequence_tick =
					0, .tick = tick_global };
	BILBO_Message_Sequencer_Event msg(event_message_data);
	sendMessage(msg);
}

/* =============================================================== */
void BILBO_Sequencer::resetSequenceData() {
	this->loaded_sequence = {
		.sequence_id = 0,
		.length = 0,
		.require_control_mode = true,
		.wait_time_beginning = 0,
		.wait_time_end = 0,
		.control_mode = bilbo_control_mode_t::OFF,
		.control_mode_end = bilbo_control_mode_t::OFF,
		.loaded = true   // no sequence pending / invalid
	};

	this->sequence_tick = 0;
}

/* =============================================================== */
twipr_sequencer_sample_t BILBO_Sequencer::getSample() {
	// Value-initialize to get deterministic defaults
	twipr_sequencer_sample_t sample { };
	sample.mode = this->mode;

	if (this->mode == TWIPR_SEQUENCER_MODE_RUNNING) {
		sample.sequence_id = this->loaded_sequence.sequence_id;
		sample.sequence_tick = this->sequence_tick;
	} else {
		sample.sequence_id = 0;
		sample.sequence_tick = 0;
	}

	return sample;
}

/* =============================================================== */
void BILBO_Sequencer::spiSequenceReceived_callback(uint16_t trajectory_length) {
	if (this->loaded_sequence.sequence_id == 0) {
		send_error("Received sequence of length %d, but did not wait for one.",
				trajectory_length);
		return;
	}

	if (this->loaded_sequence.loaded) {
		send_error("Sequence %d has already been loaded",
				this->loaded_sequence.sequence_id);
		return;
	}

	// NOTE: We still transfer TWIPR_SEQUENCE_BUFFER_SIZE elements here.
	// If you want to strictly use trajectory_length, you may want to
	// clamp it here to avoid copying unused data.
	HAL_DMA_Start_IT(
	TWIPR_FIRMWARE_TRAJECTORY_DMA_STREAM, (uint32_t) &rx_sequence_buffer,
			(uint32_t) &sequence_buffer,
			sizeof(twipr_sequence_input_t) * TWIPR_SEQUENCE_BUFFER_SIZE);
}

/* =============================================================== */
void BILBO_Sequencer::sequenceReceivedAndTransferred_callback() {
	this->loaded_sequence.loaded = true;

	sequencer_event_message_data_t event_message_data = { .event =
			TRAJECTORY_RECEIVED, .sequence_id =
			this->loaded_sequence.sequence_id, .sequence_tick = 0, .tick =
			tick_global };
	BILBO_Message_Sequencer_Event msg(event_message_data);
	sendMessage(msg);
}

/* =============================================================== */
void BILBO_Sequencer::modeChange_callback(bilbo_control_mode_t /*mode*/) {
	// If there is an active sequence, abort it on mode change.
	if (this->mode != TWIPR_SEQUENCER_MODE_RUNNING) {
		return;
	}

	this->abortSequence();
}

/* =============================================================== */
void trajectory_dma_transfer_cmplt_callback(DMA_HandleTypeDef *hdma) {
	(void) hdma;
	if (sequencer != nullptr) {
		sequencer->sequenceReceivedAndTransferred_callback();
	}
}
