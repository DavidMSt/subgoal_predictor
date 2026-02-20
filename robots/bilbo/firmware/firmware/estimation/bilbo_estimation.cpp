/*
 * bilbo_estimation.cpp
 *
 *  Created on: 22 Feb 2023
 *      Author: Dustin Lehmann
 */

#include "bilbo_estimation.h"
#include "bilbo_errors.h"
#include <cmath>

static const osThreadAttr_t estimation_task_attributes = { .name = "estimation",
		.stack_size = 1280 * 4, .priority = (osPriority_t) osPriorityNormal, };

/* ======================================================= */
BILBO_Estimation::BILBO_Estimation() :
		vqf(BILBO_ESTIMATION_TS) {
	this->status = BILBO_ESTIMATION_STATUS_NONE;
	this->vqf.setTauAcc(0.5);
}

/* ======================================================= */
void BILBO_Estimation::init(bilbo_estimation_init_config_t init_config) {
	this->init_config = init_config;

	// Velocity LPF coefficient (alpha) from cutoff frequency
	// alpha = (2*pi*fc*dt) / (1 + 2*pi*fc*dt)
	if (this->config.velocity_filter_config.enable) {
		float fc = this->config.velocity_filter_config.cutoff_hz;
		if (fc < 0.001f)
			fc = 0.001f; // avoid divide-by-zero / degenerate filter

		const float dt = BILBO_ESTIMATION_TS;
		const float omega = 2.0f * 3.14159265359f * fc;
		_v_alpha = (omega * dt) / (1.0f + omega * dt);
	} else {
		_v_alpha = 1.0f; // passthrough
	}

	_v_filt_initialized = false;

	// Theta_dot LPF coefficient
	if (this->config.theta_dot_filter_config.enable) {
		float fc = this->config.theta_dot_filter_config.cutoff_hz;
		if (fc < 0.001f)
			fc = 0.001f;

		const float dt = BILBO_ESTIMATION_TS;
		const float omega = 2.0f * 3.14159265359f * fc;
		_theta_dot_alpha = (omega * dt) / (1.0f + omega * dt);
	} else {
		_theta_dot_alpha = 1.0f;
	}

	_theta_dot_filt_initialized = false;

	// Psi_dot LPF coefficient
	if (this->config.psi_dot_filter_config.enable) {
		float fc = this->config.psi_dot_filter_config.cutoff_hz;
		if (fc < 0.001f)
			fc = 0.001f;

		const float dt = BILBO_ESTIMATION_TS;
		const float omega = 2.0f * 3.14159265359f * fc;
		_psi_dot_alpha = (omega * dt) / (1.0f + omega * dt);
	} else {
		_psi_dot_alpha = 1.0f; // passthrough
	}

	_psi_dot_filt_initialized = false;

	// Initialize position EKF
	_ekf_init();

	// Initialize the sensors
	this->status = BILBO_ESTIMATION_STATUS_IDLE;
	this->_semaphore = osSemaphoreNew(1, 1, NULL);
}

/* ======================================================= */
void BILBO_Estimation::start() {
	_v_filt_initialized = false;
	_theta_dot_filt_initialized = false;
	_psi_dot_filt_initialized = false;
	osThreadNew(estimation_task, (void*) this, &estimation_task_attributes);
}
/* ======================================================= */
void BILBO_Estimation::reset() {
	// Reset filter states
	_v_filt = 0.0f;
	_v_filt_initialized = false;
	_theta_dot_filt = 0.0f;
	_theta_dot_filt_initialized = false;
	_psi_dot_filt = 0.0f;
	_psi_dot_filt_initialized = false;

	// Reset position state to origin
	osSemaphoreAcquire(_semaphore, portMAX_DELAY);
	this->state.x = 0.0f;
	this->state.y = 0.0f;
	this->state.psi = 0.0f;
	this->position_state.x = 0.0f;
	this->position_state.y = 0.0f;
	this->position_state.psi = 0.0f;
	osSemaphoreRelease(_semaphore);

	// Reset EKF
	_ekf_init();
	_position_update_available = false;
	_is_dead_reckoning = true;
	_dead_reckoning_counter = this->config.position_ekf_config.dead_reckoning_timeout;
}
/* ======================================================= */
void BILBO_Estimation::task_function() {

//	this->_orientation_fusion.begin((float) BILBO_ESTIMATION_FREQUENCY);
	this->status = BILBO_ESTIMATION_STATUS_OK;
//	this->_sensors.calibrate();
	uint32_t ticks;

	while (true) {
		ticks = osKernelGetTickCount();
		this->update();
		osDelayUntil(ticks + (uint32_t) (1000.0 / BILBO_ESTIMATION_FREQUENCY));
	}
}
/* ======================================================= */
void BILBO_Estimation::stop() {

}
/* ======================================================= */
void BILBO_Estimation::update() {

	// Update the Sensors
	this->init_config.sensors->update();

	// Read the sensor data
	bilbo_sensors_data_t data = this->init_config.sensors->getData();

	// Orientation Estimation
	vqf_real_t gyr[3] = { data.gyr.x, data.gyr.y, data.gyr.z };
	vqf_real_t acc[3] = { data.acc.x, data.acc.y, data.acc.z };
	vqf.update(gyr, acc);

	vqf_real_t quat[4];

	vqf.getQuat6D(quat);
	float w = quat[0];
	float x = quat[1];
	float y = quat[2];
	float z = quat[3];

	float theta = atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y));

	float theta_dot_raw = data.gyr.x;
	float theta_dot = theta_dot_raw;
	if (this->config.theta_dot_filter_config.enable) {
		theta_dot = this->_lpf_theta_dot_update(theta_dot_raw);
	} else {
		_theta_dot_filt = theta_dot_raw;
		_theta_dot_filt_initialized = true;
	}

	// Correct the speed by the pitch angle velocity
	data.speed_left += theta_dot;
	data.speed_right += theta_dot;


	// Get the speed and yaw speed
	float v_raw = ((data.speed_left + data.speed_right) / 2) * WHEEL_DIAMETER
			/ 2;


	float v = v_raw;
	if (this->config.velocity_filter_config.enable) {
		v = this->_lpf1_update(v_raw);
	} else {
		// keep filter state reasonable if someone toggles enable at runtime
		_v_filt = v_raw;
		_v_filt_initialized = true;
	}

	float psi_dot_raw = (data.speed_right - data.speed_left)
			* (WHEEL_DIAMETER / 2) / WHEEL_DISTANCE;

	// Psi_dot LPF
	float psi_dot = psi_dot_raw;
	if (this->config.psi_dot_filter_config.enable) {
		psi_dot = this->_lpf_psi_dot_update(psi_dot_raw);
	} else {
		_psi_dot_filt = psi_dot_raw;
		_psi_dot_filt_initialized = true;
	}

	// Position EKF - prediction step (dead-reckoning) and OptiTrack updates
	if (this->config.position_ekf_config.enable) {
		// EKF enabled: run prediction (dead-reckoning) and fuse with OptiTrack
		_ekf_predict(v, psi_dot, BILBO_ESTIMATION_TS);

		// Check for OptiTrack update
		if (_position_update_available) {
			_ekf_update(_position_update);
			_position_update_available = false;
			_dead_reckoning_counter = 0;
			_is_dead_reckoning = false;
		} else {
			// Increment counter and check timeout
			_dead_reckoning_counter++;
			if (_dead_reckoning_counter >= this->config.position_ekf_config.dead_reckoning_timeout) {
				_is_dead_reckoning = true;
			}
		}
	} else {
		// EKF disabled: use OptiTrack position directly without dead-reckoning
		if (_position_update_available) {
			// Directly set position from OptiTrack (no EKF fusion)
			this->position_state.x = _position_update.x;
			this->position_state.y = _position_update.y;
			this->position_state.psi = _position_update.psi;
			_position_update_available = false;
			_dead_reckoning_counter = 0;
			_is_dead_reckoning = false;
		} else {
			// No OptiTrack update and no dead-reckoning - position is stale
			_dead_reckoning_counter++;
			if (_dead_reckoning_counter >= this->config.position_ekf_config.dead_reckoning_timeout) {
				_is_dead_reckoning = true;
			}
		}
	}

	// Set the current state
	osSemaphoreAcquire(_semaphore, portMAX_DELAY);
	this->state.v = v;
	this->state.theta = theta + this->_theta_offset;
	this->state.theta_dot = theta_dot;
	this->state.psi = this->position_state.psi;
	this->state.psi_dot = psi_dot;
	this->state.x = this->position_state.x;
	this->state.y = this->position_state.y;

	// Calculate the average
	this->mean_state.v = this->mean_state.v
			- (this->_state_buffer[this->_state_buffer_index].v
					/ (float) BILBO_ESTIMATION_STATE_BUFFER_SIZE)
			+ (this->state.v / (float) BILBO_ESTIMATION_STATE_BUFFER_SIZE);
	this->mean_state.theta = this->mean_state.theta
			- (this->_state_buffer[this->_state_buffer_index].theta
					/ (float) BILBO_ESTIMATION_STATE_BUFFER_SIZE)
			+ (this->state.theta / (float) BILBO_ESTIMATION_STATE_BUFFER_SIZE);
	this->mean_state.theta_dot = this->mean_state.theta_dot
			- (this->_state_buffer[this->_state_buffer_index].theta_dot
					/ (float) BILBO_ESTIMATION_STATE_BUFFER_SIZE)
			+ (this->state.theta_dot
					/ (float) BILBO_ESTIMATION_STATE_BUFFER_SIZE);
	this->mean_state.psi = this->mean_state.psi
			- (this->_state_buffer[this->_state_buffer_index].psi
					/ (float) BILBO_ESTIMATION_STATE_BUFFER_SIZE)
			+ (this->state.psi / (float) BILBO_ESTIMATION_STATE_BUFFER_SIZE);
	this->mean_state.psi_dot =
			this->mean_state.psi_dot
					- (this->_state_buffer[this->_state_buffer_index].psi_dot
							/ (float) BILBO_ESTIMATION_STATE_BUFFER_SIZE)
					+ (this->state.psi_dot
							/ (float) BILBO_ESTIMATION_STATE_BUFFER_SIZE);

	this->_state_buffer[this->_state_buffer_index] = this->state;
	osSemaphoreRelease(_semaphore);

	this->_state_buffer_index++;
	if (this->_state_buffer_index == BILBO_ESTIMATION_STATE_BUFFER_SIZE) {
		this->_state_buffer_index = 0;
	}

}

/* ======================================================= */
bool BILBO_Estimation::setThetaOffset(float offset) {
	this->_theta_offset = offset;
	return true;
}
/* ======================================================= */
bilbo_estimation_state_t BILBO_Estimation::getMeanState() {
	bilbo_estimation_state_t out;
	osSemaphoreAcquire(_semaphore, portMAX_DELAY);
	out = this->mean_state;
	osSemaphoreRelease(_semaphore);
	return out;
}
/* ======================================================= */
bilbo_estimation_state_t BILBO_Estimation::getState() {
	osSemaphoreAcquire(_semaphore, portMAX_DELAY);
	bilbo_estimation_state_t out = this->state;
	osSemaphoreRelease(_semaphore);
	return out;
}
/* ======================================================= */
void BILBO_Estimation::setState(bilbo_estimation_state_t state) {

//	bilbo_error_handler(0);
}
/* ======================================================= */
void BILBO_Estimation::set_position_state(
		bilbo_position_state_t position_state) {
	this->position_state = position_state;
}
/* ======================================================= */
bilbo_logging_estimation_t BILBO_Estimation::getSample() {
	bilbo_logging_estimation_t sample;
	sample.state = this->getState();
	sample.is_dead_reckoning = _is_dead_reckoning;
	return sample;
}
/* ======================================================= */
inline float BILBO_Estimation::_lpf1_update(float x) {
	// Optional "initialize on first sample"
	if (this->config.velocity_filter_config.reset_on_start
			&& !_v_filt_initialized) {
		_v_filt = x;
		_v_filt_initialized = true;
		return _v_filt;
	}

	// First-order IIR: y += alpha * (x - y)
	_v_filt += _v_alpha * (x - _v_filt);
	return _v_filt;
}
/* ======================================================= */

/* ======================================================= */
void BILBO_Estimation::set_position_update(bilbo_position_state_t position_state) {
	_position_update = position_state;
	_position_update_available = true;
}
/* ======================================================= */
velocity_lowpass_filter_config_t BILBO_Estimation::get_velocity_lpf_config() {
	return this->config.velocity_filter_config;
}
/* ======================================================= */
void BILBO_Estimation::set_velocity_lpf_config(velocity_lowpass_filter_config_t new_config) {
	this->config.velocity_filter_config = new_config;

	// Recalculate filter coefficient
	if (this->config.velocity_filter_config.enable) {
		float fc = this->config.velocity_filter_config.cutoff_hz;
		if (fc < 0.001f)
			fc = 0.001f;

		const float dt = BILBO_ESTIMATION_TS;
		const float omega = 2.0f * 3.14159265359f * fc;
		_v_alpha = (omega * dt) / (1.0f + omega * dt);
	} else {
		_v_alpha = 1.0f; // passthrough
	}

	// Reset filter state
	_v_filt_initialized = false;
}
/* ======================================================= */
theta_dot_lowpass_filter_config_t BILBO_Estimation::get_theta_dot_lpf_config() {
	return this->config.theta_dot_filter_config;
}
/* ======================================================= */
void BILBO_Estimation::set_theta_dot_lpf_config(theta_dot_lowpass_filter_config_t new_config) {
	this->config.theta_dot_filter_config = new_config;

	if (this->config.theta_dot_filter_config.enable) {
		float fc = this->config.theta_dot_filter_config.cutoff_hz;
		if (fc < 0.001f)
			fc = 0.001f;

		const float dt = BILBO_ESTIMATION_TS;
		const float omega = 2.0f * 3.14159265359f * fc;
		_theta_dot_alpha = (omega * dt) / (1.0f + omega * dt);
	} else {
		_theta_dot_alpha = 1.0f;
	}

	_theta_dot_filt_initialized = false;
}
/* ======================================================= */
psi_dot_lowpass_filter_config_t BILBO_Estimation::get_psi_dot_lpf_config() {
	return this->config.psi_dot_filter_config;
}
/* ======================================================= */
void BILBO_Estimation::set_psi_dot_lpf_config(psi_dot_lowpass_filter_config_t new_config) {
	this->config.psi_dot_filter_config = new_config;

	// Recalculate filter coefficient
	if (this->config.psi_dot_filter_config.enable) {
		float fc = this->config.psi_dot_filter_config.cutoff_hz;
		if (fc < 0.001f)
			fc = 0.001f;

		const float dt = BILBO_ESTIMATION_TS;
		const float omega = 2.0f * 3.14159265359f * fc;
		_psi_dot_alpha = (omega * dt) / (1.0f + omega * dt);
	} else {
		_psi_dot_alpha = 1.0f; // passthrough
	}

	// Reset filter state
	_psi_dot_filt_initialized = false;
}
/* ======================================================= */
inline float BILBO_Estimation::_lpf_theta_dot_update(float x) {
	if (this->config.theta_dot_filter_config.reset_on_start
			&& !_theta_dot_filt_initialized) {
		_theta_dot_filt = x;
		_theta_dot_filt_initialized = true;
		return _theta_dot_filt;
	}

	_theta_dot_filt += _theta_dot_alpha * (x - _theta_dot_filt);
	return _theta_dot_filt;
}
/* ======================================================= */
inline float BILBO_Estimation::_lpf_psi_dot_update(float x) {
	// Optional "initialize on first sample"
	if (this->config.psi_dot_filter_config.reset_on_start
			&& !_psi_dot_filt_initialized) {
		_psi_dot_filt = x;
		_psi_dot_filt_initialized = true;
		return _psi_dot_filt;
	}

	// First-order IIR: y += alpha * (x - y)
	_psi_dot_filt += _psi_dot_alpha * (x - _psi_dot_filt);
	return _psi_dot_filt;
}
/* ======================================================= */
bilbo_estimation_config_t BILBO_Estimation::get_config() {
	return this->config;
}
/* ======================================================= */
void BILBO_Estimation::set_config(bilbo_estimation_config_t new_config) {
	this->config = new_config;

	// Recalculate velocity LPF coefficient
	if (this->config.velocity_filter_config.enable) {
		float fc = this->config.velocity_filter_config.cutoff_hz;
		if (fc < 0.001f) fc = 0.001f;
		const float dt = BILBO_ESTIMATION_TS;
		const float omega = 2.0f * 3.14159265359f * fc;
		_v_alpha = (omega * dt) / (1.0f + omega * dt);
	} else {
		_v_alpha = 1.0f;
	}
	_v_filt_initialized = false;

	// Recalculate theta_dot LPF coefficient
	if (this->config.theta_dot_filter_config.enable) {
		float fc = this->config.theta_dot_filter_config.cutoff_hz;
		if (fc < 0.001f) fc = 0.001f;
		const float dt = BILBO_ESTIMATION_TS;
		const float omega = 2.0f * 3.14159265359f * fc;
		_theta_dot_alpha = (omega * dt) / (1.0f + omega * dt);
	} else {
		_theta_dot_alpha = 1.0f;
	}
	_theta_dot_filt_initialized = false;

	// Recalculate psi_dot LPF coefficient
	if (this->config.psi_dot_filter_config.enable) {
		float fc = this->config.psi_dot_filter_config.cutoff_hz;
		if (fc < 0.001f) fc = 0.001f;
		const float dt = BILBO_ESTIMATION_TS;
		const float omega = 2.0f * 3.14159265359f * fc;
		_psi_dot_alpha = (omega * dt) / (1.0f + omega * dt);
	} else {
		_psi_dot_alpha = 1.0f;
	}
	_psi_dot_filt_initialized = false;
}
/* ======================================================= */
void BILBO_Estimation::set_dead_reckoning_enable(bool enable) {
	this->config.position_ekf_config.enable = enable;
	if (!enable) {
		// When disabling, reset to pure optitrack mode (if available)
		_is_dead_reckoning = true;
	}
}
/* ======================================================= */
void BILBO_Estimation::_ekf_init() {
	// Initialize position state to zero
	this->position_state.x = 0.0f;
	this->position_state.y = 0.0f;
	this->position_state.psi = 0.0f;

	// Initialize covariance matrix P with initial uncertainty
	// Start with moderate uncertainty since we don't know initial position
	for (int i = 0; i < 3; i++) {
		for (int j = 0; j < 3; j++) {
			_ekf_P[i][j] = 0.0f;
		}
	}
	_ekf_P[0][0] = 0.01f;  // x variance (10cm std dev initially)
	_ekf_P[1][1] = 0.01f;  // y variance
	_ekf_P[2][2] = 0.01f;  // psi variance (~6 deg)

	_ekf_initialized = true;
	_is_dead_reckoning = true;
	_dead_reckoning_counter = this->config.position_ekf_config.dead_reckoning_timeout; // start in dead-reckoning mode
}
/* ======================================================= */
void BILBO_Estimation::_ekf_predict(float v, float psi_dot, float dt) {
	// Current state
	float x = this->position_state.x;
	float y = this->position_state.y;
	float psi = this->position_state.psi;

	// State prediction (simple forward integration)
	// x_new = x + v * cos(psi) * dt
	// y_new = y + v * sin(psi) * dt
	// psi_new = psi + psi_dot * dt
	float cos_psi = cosf(psi);
	float sin_psi = sinf(psi);

	this->position_state.x = x + v * cos_psi * dt;
	this->position_state.y = y + v * sin_psi * dt;
	this->position_state.psi = psi + psi_dot * dt;

	// Normalize psi to [-pi, pi]
	while (this->position_state.psi > 3.14159265359f)
		this->position_state.psi -= 2.0f * 3.14159265359f;
	while (this->position_state.psi < -3.14159265359f)
		this->position_state.psi += 2.0f * 3.14159265359f;

	// Jacobian of state transition (F = df/dx)
	// F = [1, 0, -v*sin(psi)*dt]
	//     [0, 1,  v*cos(psi)*dt]
	//     [0, 0,  1            ]
	float F_02 = -v * sin_psi * dt;
	float F_12 = v * cos_psi * dt;

	// Process noise Q - velocity/psi_dot integration noise
	// Noise scales with speed: faster motion = more uncertainty
	// Base noise + speed-dependent component
	float abs_v = (v >= 0) ? v : -v;
	float abs_psi_dot = (psi_dot >= 0) ? psi_dot : -psi_dot;

	// Velocity noise from config
	float sigma_v = this->config.position_ekf_config.sigma_v_base
			+ this->config.position_ekf_config.sigma_v_scale * abs_v;
	// Psi_dot noise from config
	float sigma_psi_dot = this->config.position_ekf_config.sigma_psi_dot_base
			+ this->config.position_ekf_config.sigma_psi_dot_scale * abs_psi_dot;

	// Process noise variances (integrated over dt)
	float q_pos = sigma_v * sigma_v * dt * dt;  // position variance from velocity noise
	float q_psi = sigma_psi_dot * sigma_psi_dot * dt * dt;  // psi variance from psi_dot noise

	// Q matrix (simplified diagonal approximation)
	float Q[3][3] = {
		{q_pos, 0.0f, 0.0f},
		{0.0f, q_pos, 0.0f},
		{0.0f, 0.0f, q_psi}
	};

	// Covariance prediction: P = F * P * F^T + Q
	// Since F is mostly identity, compute efficiently:
	// P_new[i][j] = P[i][j] + F[i][2]*P[2][j] + P[i][2]*F[j][2] + F[i][2]*P[2][2]*F[j][2] + Q[i][j]

	float P_new[3][3];

	// Row 0
	P_new[0][0] = _ekf_P[0][0] + F_02 * _ekf_P[2][0] + _ekf_P[0][2] * F_02 + F_02 * _ekf_P[2][2] * F_02 + Q[0][0];
	P_new[0][1] = _ekf_P[0][1] + F_02 * _ekf_P[2][1] + _ekf_P[0][2] * F_12 + F_02 * _ekf_P[2][2] * F_12;
	P_new[0][2] = _ekf_P[0][2] + F_02 * _ekf_P[2][2];

	// Row 1
	P_new[1][0] = _ekf_P[1][0] + F_12 * _ekf_P[2][0] + _ekf_P[1][2] * F_02 + F_12 * _ekf_P[2][2] * F_02;
	P_new[1][1] = _ekf_P[1][1] + F_12 * _ekf_P[2][1] + _ekf_P[1][2] * F_12 + F_12 * _ekf_P[2][2] * F_12 + Q[1][1];
	P_new[1][2] = _ekf_P[1][2] + F_12 * _ekf_P[2][2];

	// Row 2
	P_new[2][0] = _ekf_P[2][0] + _ekf_P[2][2] * F_02;
	P_new[2][1] = _ekf_P[2][1] + _ekf_P[2][2] * F_12;
	P_new[2][2] = _ekf_P[2][2] + Q[2][2];

	// Copy back
	for (int i = 0; i < 3; i++) {
		for (int j = 0; j < 3; j++) {
			_ekf_P[i][j] = P_new[i][j];
		}
	}
}
/* ======================================================= */
void BILBO_Estimation::_ekf_update(bilbo_position_state_t measurement) {
	// SIMPLIFIED VERSION FOR TESTING: Directly set state to measurement
	// (bypasses EKF fusion, treats measurement as ground truth)
	this->position_state.x = measurement.x;
	this->position_state.y = measurement.y;
	this->position_state.psi = measurement.psi;

	// Reset covariance to small values since we trust the measurement
	_ekf_P[0][0] = 0.001f;
	_ekf_P[1][1] = 0.001f;
	_ekf_P[2][2] = 0.001f;

	/*
	// ORIGINAL EKF UPDATE - COMMENTED OUT FOR TESTING
	// Measurement model: z = H * x, where H = I (identity)
	// So innovation y = z - x (direct state measurement)

	float y[3];
	y[0] = measurement.x - this->position_state.x;
	y[1] = measurement.y - this->position_state.y;
	y[2] = measurement.psi - this->position_state.psi;

	// Handle angle wrapping for psi innovation
	while (y[2] > 3.14159265359f)
		y[2] -= 2.0f * 3.14159265359f;
	while (y[2] < -3.14159265359f)
		y[2] += 2.0f * 3.14159265359f;

	// Measurement noise R (from config)
	float std_pos = this->config.position_ekf_config.std_dev_position;
	float std_psi = this->config.position_ekf_config.std_dev_psi;

	float R[3][3] = {
		{std_pos * std_pos, 0.0f, 0.0f},
		{0.0f, std_pos * std_pos, 0.0f},
		{0.0f, 0.0f, std_psi * std_psi}
	};

	// Since H = I, innovation covariance S = P + R
	float S[3][3];
	for (int i = 0; i < 3; i++) {
		for (int j = 0; j < 3; j++) {
			S[i][j] = _ekf_P[i][j] + R[i][j];
		}
	}

	// Kalman gain K = P * H^T * S^(-1) = P * S^(-1)
	// For 3x3, compute inverse of S
	float det = S[0][0] * (S[1][1] * S[2][2] - S[1][2] * S[2][1])
	          - S[0][1] * (S[1][0] * S[2][2] - S[1][2] * S[2][0])
	          + S[0][2] * (S[1][0] * S[2][1] - S[1][1] * S[2][0]);

	if (det < 1e-10f && det > -1e-10f) {
		// Singular matrix, skip update
		return;
	}

	float inv_det = 1.0f / det;

	float S_inv[3][3];
	S_inv[0][0] = (S[1][1] * S[2][2] - S[1][2] * S[2][1]) * inv_det;
	S_inv[0][1] = (S[0][2] * S[2][1] - S[0][1] * S[2][2]) * inv_det;
	S_inv[0][2] = (S[0][1] * S[1][2] - S[0][2] * S[1][1]) * inv_det;
	S_inv[1][0] = (S[1][2] * S[2][0] - S[1][0] * S[2][2]) * inv_det;
	S_inv[1][1] = (S[0][0] * S[2][2] - S[0][2] * S[2][0]) * inv_det;
	S_inv[1][2] = (S[0][2] * S[1][0] - S[0][0] * S[1][2]) * inv_det;
	S_inv[2][0] = (S[1][0] * S[2][1] - S[1][1] * S[2][0]) * inv_det;
	S_inv[2][1] = (S[0][1] * S[2][0] - S[0][0] * S[2][1]) * inv_det;
	S_inv[2][2] = (S[0][0] * S[1][1] - S[0][1] * S[1][0]) * inv_det;

	// K = P * S_inv
	float K[3][3];
	for (int i = 0; i < 3; i++) {
		for (int j = 0; j < 3; j++) {
			K[i][j] = 0.0f;
			for (int k = 0; k < 3; k++) {
				K[i][j] += _ekf_P[i][k] * S_inv[k][j];
			}
		}
	}

	// State update: x = x + K * y
	float dx[3] = {0.0f, 0.0f, 0.0f};
	for (int i = 0; i < 3; i++) {
		for (int j = 0; j < 3; j++) {
			dx[i] += K[i][j] * y[j];
		}
	}

	this->position_state.x += dx[0];
	this->position_state.y += dx[1];
	this->position_state.psi += dx[2];

	// Normalize psi
	while (this->position_state.psi > 3.14159265359f)
		this->position_state.psi -= 2.0f * 3.14159265359f;
	while (this->position_state.psi < -3.14159265359f)
		this->position_state.psi += 2.0f * 3.14159265359f;

	// Covariance update: P = (I - K*H) * P = (I - K) * P
	float I_minus_K[3][3];
	for (int i = 0; i < 3; i++) {
		for (int j = 0; j < 3; j++) {
			I_minus_K[i][j] = ((i == j) ? 1.0f : 0.0f) - K[i][j];
		}
	}

	float P_new[3][3];
	for (int i = 0; i < 3; i++) {
		for (int j = 0; j < 3; j++) {
			P_new[i][j] = 0.0f;
			for (int k = 0; k < 3; k++) {
				P_new[i][j] += I_minus_K[i][k] * _ekf_P[k][j];
			}
		}
	}

	for (int i = 0; i < 3; i++) {
		for (int j = 0; j < 3; j++) {
			_ekf_P[i][j] = P_new[i][j];
		}
	}

	// Enforce minimum covariance floor to prevent P from getting too small
	// This ensures the filter remains responsive to measurements
	float min_pos_var = this->config.position_ekf_config.min_position_variance;
	float min_psi_var = this->config.position_ekf_config.min_psi_variance;
	if (_ekf_P[0][0] < min_pos_var) _ekf_P[0][0] = min_pos_var;
	if (_ekf_P[1][1] < min_pos_var) _ekf_P[1][1] = min_pos_var;
	if (_ekf_P[2][2] < min_psi_var) _ekf_P[2][2] = min_psi_var;
	*/
}
/* ======================================================= */
void estimation_task(void *estimation) {
	BILBO_Estimation *estimator = (BILBO_Estimation*) estimation;
	estimator->task_function();
}
