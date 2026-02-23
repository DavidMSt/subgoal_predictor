/*
 * firmware_defs.h
 *
 *  Created on: 16 Mar 2023
 *      Author: lehmann_workstation
 */

#ifndef FIRMWARE_DEFS_H_
#define FIRMWARE_DEFS_H_

#include "core.h"
#include "firmware_settings.h"


// ------------------------------------------------------------------------------------------------ //
typedef struct bilbo_firmware_revision_t {
	uint8_t major;
	uint8_t minor;
}bilbo_firmware_revision_t;


typedef enum bilbo_firmware_state_t {
	BILBO_FIRMWARE_STATE_ERROR = -1,
	BILBO_FIRMWARE_STATE_RUNNING = 1,
	BILBO_FIRMWARE_STATE_NONE = 0,
} bilbo_firmware_state_t;

typedef struct bilbo_logging_general_t {
	bilbo_firmware_state_t state;
} bilbo_logging_general_t;

#define BILBO_FIRMWARE_SAMPLE_BUFFER_SIZE (uint16_t) (BILBO_FIRMWARE_SAMPLE_BUFFER_TIME * 1000 / BILBO_CONTROL_TS_MS)
#define BILBO_SEQUENCE_BUFFER_SIZE (uint32_t) (BILBO_SEQUENCE_TIME * 1000/BILBO_CONTROL_TS_MS)
#define BILBO_CONTROL_TS_MS (uint32_t) (1000.0 / BILBO_CONTROL_TASK_FREQ)

#ifdef BILBO_DRIVE_SIMPLEXMOTION_RS485
#define BILBO_DRIVE_TYPE BILBO_DRIVE_SM_RS485
#define BILBO_DRIVE_TASK_TIME 20
#endif

#ifdef BILBO_DRIVE_SIMPLEXMOTION_CAN
#define BILBO_DRIVE_TYPE BILBO_DRIVE_SM_CAN
#define BILBO_DRIVE_TASK_TIME 10
#endif


extern DMA_HandleTypeDef hdma_memtomem_dma2_stream0;
#define BILBO_FIRMWARE_SAMPLE_DMA_STREAM &hdma_memtomem_dma2_stream0

extern DMA_HandleTypeDef hdma_memtomem_dma2_stream1;
#define BILBO_FIRMWARE_TRAJECTORY_DMA_STREAM &hdma_memtomem_dma2_stream1

#endif /* FIRMWARE_DEFS_H_ */

