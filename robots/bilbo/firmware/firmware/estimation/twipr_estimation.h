/*
 * twipr_estimation.h
 *
 *  Created on: 22 Feb 2023
 *      Author: Dustin Lehmann
 */

#ifndef ESTIMATION_TWIPR_ESTIMATION_H_
#define ESTIMATION_TWIPR_ESTIMATION_H_

#include "core.h"
#include "twipr_model.h"
#include "twipr_sensors.h"
#include "vqf.hpp"
#include "basicvqf.hpp"

#define TWIPR_ESTIMATION_FREQUENCY 100
#define TWIPR_ESTIMATION_TS 0.01
#define TWIPR_ESTIMATION_STATE_BUFFER_SIZE TWIPR_ESTIMATION_FREQUENCY*1

typedef enum twipr_estimation_status_t {
	TWIPR_ESTIMATION_STATUS_NONE = 0,
	TWIPR_ESTIMATION_STATUS_IDLE = 1,
	TWIPR_ESTIMATION_STATUS_OK = 2,
	TWIPR_ESTIMATION_STATUS_ERROR = -1,
} twipr_estimation_status_t;

typedef struct twipr_estimation_state_t {
	float x; // new
	float y; // new
	float v;
	float theta;
	float theta_dot;
	float psi;
	float psi_dot;
} twipr_estimation_state_t;

typedef struct bilbo_position_state_t {
	float x;
	float y;
	float psi;
} bilbo_position_state_t;

typedef enum twipr_estimation_callback_id {
	TWIPR_ESTIMATION_CALLBACK_UPDATE = 0,
	TWIPR_ESTIMATION_CALLBACK_ERROR = 1,
	TWIPR_ESTIMATION_CALLBACK_ANGLE = 2,
	TWIPR_ESTIMATION_CALLBACK_SLIP = 3,
} twipr_estimation_callback_id;

typedef struct twipr_estimation_callbacks {
	core_utils_Callback<void, void> update;
	core_utils_Callback<void, void> error;
	core_utils_Callback<void, void> angle;
	core_utils_Callback<void, void> slip;
} twipr_estimation_callbacks;

struct velocity_lowpass_filter_config_t {
	bool enable = true;        // on/off
	float cutoff_hz = 30.0f;    // LPF cutoff frequency in Hz (typical: 5..30)
	bool reset_on_start = true; // initialize filter output with first sample
};

// NEW
struct psi_dot_lowpass_filter_config_t {
	bool enable = true;        // on/off
	float cutoff_hz = 30.0f;    // LPF cutoff frequency in Hz (typical: 5..30)
	bool reset_on_start = true; // initialize filter output with first sample
};

/**
 * Configuration for the Position EKF (Extended Kalman Filter)
 *
 * The EKF estimates the robot's position [x, y, psi] by fusing:
 * - Dead-reckoning: Forward integration of velocity and yaw rate
 *   x += v * cos(psi) * dt
 *   y += v * sin(psi) * dt
 *   psi += psi_dot * dt
 * - External measurements: Position updates from OptiTrack via set_position_update()
 *
 * Process noise model (velocity/psi_dot integration uncertainty):
 *   sigma_v = sigma_v_base + sigma_v_scale * |v|
 *   sigma_psi_dot = sigma_psi_dot_base + sigma_psi_dot_scale * |psi_dot|
 * This models increased uncertainty at higher speeds due to wheel slip, etc.
 *
 * Dead-reckoning detection:
 *   If no position update is received for 'dead_reckoning_timeout' consecutive
 *   update cycles, the is_dead_reckoning flag is set to true.
 */
struct position_ekf_config_t {
	bool enable = true;

	// Measurement noise (OptiTrack)
	float std_dev_position = 0.0005f;   // position measurement std dev (m), ~0.5mm for OptiTrack
	float std_dev_psi = 0.005f;         // heading measurement std dev (rad), ~0.3 deg

	// Process noise - velocity integration
	float sigma_v_base = 0.10f;         // base velocity noise (m/s) - higher = trust dead-reckoning less
	float sigma_v_scale = 0.10f;        // velocity noise scaling factor (fraction of |v|)

	// Process noise - psi_dot integration
	float sigma_psi_dot_base = 0.15f;   // base psi_dot noise (rad/s)
	float sigma_psi_dot_scale = 0.15f;  // psi_dot noise scaling factor (fraction of |psi_dot|)

	// Minimum covariance floor (prevents P from getting too small)
	float min_position_variance = 0.0001f;  // minimum position variance (m²), ~1cm std dev
	float min_psi_variance = 0.001f;        // minimum psi variance (rad²), ~1.8 deg std dev

	// Dead-reckoning detection
	uint16_t dead_reckoning_timeout = 10; // number of updates without measurement before flagging dead-reckoning
};

typedef struct twipr_estimation_config_t {
	BILBO_Drive *drive;
	TWIPR_Sensors *sensors;
	velocity_lowpass_filter_config_t velocity_filter_config; // new
	psi_dot_lowpass_filter_config_t psi_dot_filter_config; // new
	position_ekf_config_t position_ekf_config; // new
} twipr_estimation_config_t;

typedef struct twipr_logging_estimation_t {
	twipr_estimation_state_t state;
	bool is_dead_reckoning; // new
} twipr_logging_estimation_t;

class TWIPR_Estimation {
public:
	TWIPR_Estimation();
	void init(twipr_estimation_config_t config);
	void start();
	void reset();
	void stop();

	void update();

	void task_function();

	twipr_logging_estimation_t getSample();

	void registerCallback(twipr_estimation_callback_id callback_id,
			void (*callback)(void *argument, void *params), void *params);

	twipr_estimation_state_t getState();
	twipr_estimation_state_t getMeanState();

	void setState(twipr_estimation_state_t state);

	bool setThetaOffset(float offset);

	twipr_estimation_status_t getStatus();

	void set_position_state(bilbo_position_state_t position_state);
	void set_position_update(bilbo_position_state_t position_state); // new

	// Velocity LPF config get/set
	velocity_lowpass_filter_config_t get_velocity_lpf_config();
	void set_velocity_lpf_config(velocity_lowpass_filter_config_t config);

	// Psi_dot LPF config get/set
	psi_dot_lowpass_filter_config_t get_psi_dot_lpf_config();
	void set_psi_dot_lpf_config(psi_dot_lowpass_filter_config_t config);

	// Dead-reckoning EKF enable/disable
	void set_dead_reckoning_enable(bool enable);

	twipr_estimation_status_t status;
	twipr_estimation_state_t state;
	twipr_estimation_state_t mean_state;
	twipr_estimation_config_t config;

	bilbo_position_state_t position_state;
private:
	uint16_t _freq;
	twipr_estimation_state_t _state_buffer[TWIPR_ESTIMATION_STATE_BUFFER_SIZE];
	uint16_t _state_buffer_index = 0;
	osSemaphoreId_t _semaphore;
//	Madgwick _orientation_fusion;
	BasicVQF vqf;
	float _theta_offset = 0;

	// Velocity LPF
	float _v_alpha = 1.0f;          // filter coefficient
	float _v_filt = 0.0f;           // filtered velocity
	bool _v_filt_initialized = false;

	inline float _lpf1_update(float x);

	// Psi_dot LPF
	float _psi_dot_alpha = 1.0f;    // filter coefficient
	float _psi_dot_filt = 0.0f;     // filtered psi_dot
	bool _psi_dot_filt_initialized = false;

	inline float _lpf_psi_dot_update(float x);

	// Position EKF for dead-reckoning with OptiTrack updates
	// State: [x, y, psi]
	float _ekf_P[3][3];             // covariance matrix
	bool _ekf_initialized = false;
	bool _is_dead_reckoning = true; // true if no recent OptiTrack update
	uint16_t _dead_reckoning_counter = 0; // counts updates since last position measurement

	void _ekf_init();
	void _ekf_predict(float v, float psi_dot, float dt);
	void _ekf_update(bilbo_position_state_t measurement);

	bilbo_position_state_t _position_update; // new: position from optitrack
	bool _position_update_available = false;

};

void estimation_task(void *estimation);

#endif /* ESTIMATION_TWIPR_ESTIMATION_H_ */
