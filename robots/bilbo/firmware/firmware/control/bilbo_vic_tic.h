/*
 * bilbo_vic_tic.h
 *
 *  Created on: Jan 11, 2026
 *      Author: lehmann
 */

#ifndef CONTROL_BILBO_VIC_TIC_H_
#define CONTROL_BILBO_VIC_TIC_H_
#include <cmath>
/* ---------------------------------------------------------------------------------------- */
struct bilbo_tic_config_t {
	uint8_t enabled;
	float Ts;
	float ki;
	float max_torque;
	float theta_limit;
};

struct bilbo_tic_callbacks_t {
	core_utils_CallbackContainer<4, void> disable;
};

/* ---------------------------------------------------------------------------------------- */
class BILBO_TIC_Controller {
public:
	BILBO_TIC_Controller() :
			_integral_torque(0.0f) {
	}

	void init(bilbo_tic_config_t config) {
		this->config = config;
		this->_integral_torque = 0.0f;
		this->enabled = config.enabled;
	}

	void set_enabled(bool state) {
		if (!this->config.enabled) {
			this->enabled = false;
			this->reset();
			return;
		}

		if (this->enabled != state) {
			this->reset();
		}
		this->enabled = state;
	}

	void set_config(bilbo_tic_config_t config) {
		this->config = config;
		if (!this->config.enabled) {
			this->enabled = false;
		}
		this->reset();
	}

	// Methods
	float update(float theta) {
		if (this->config.enabled == false || this->enabled == false) {
			return 0.0f;
		}

		if (this->config.theta_limit != 0.0f) {
			if (std::fabs(theta) > this->config.theta_limit) {
				this->reset();
				this->enabled = false;
				this->callbacks.disable.call();
				return 0.0f;
			}
		}

		// Integrate torque directly: I_tau += ki * theta * Ts
		this->_integral_torque += (this->config.ki * theta * this->config.Ts);

		// Clamp directly in torque units
		if (this->config.max_torque > 0.0f) {
			if (this->_integral_torque > this->config.max_torque) {
				this->_integral_torque = this->config.max_torque;
			} else if (this->_integral_torque < -this->config.max_torque) {
				this->_integral_torque = -this->config.max_torque;
			}
		}

		// Output is already torque
		return this->_integral_torque;
	}

	void reset() {
		this->_integral_torque = 0.0f;
	}
	bool is_enabled() const {
		return this->enabled;
	}

	bilbo_tic_config_t config;
	bilbo_tic_callbacks_t callbacks;
private:
	bool enabled = false;

	float _integral_torque; // stores integral in torque units
};

/* ======================================================================================== */
struct bilbo_vic_config_t {
	uint8_t enabled;
	float Ts;
	float ki;
	float max_torque;
	float v_limit;
	float theta_limit;
};

//struct bilbo_vic_callbacks_t {
//	core_utils_CallbackContainer<4, void> enabled;
//	core_utils_CallbackContainer<4, void> disabled;
//	core_utils_CallbackContainer<4, void> enable_change;
//};

/* ---------------------------------------------------------------------------------------- */
class BILBO_VIC_Controller {
public:
	BILBO_VIC_Controller() :
			_integral_torque(0.0f) {
	}

	void init(bilbo_vic_config_t config) {
		this->config = config;
		this->_integral_torque = 0.0f;
		this->enabled = config.enabled;
	}

	void set_enabled(bool state) {
		if (!this->config.enabled) {
			this->enabled = false;
			this->reset();
			return;
		}

		if (this->enabled != state) {
			this->reset();
		}
		this->enabled = state;
	}

	void set_config(bilbo_vic_config_t config) {
		this->config = config;

		if (!this->config.enabled) {
			this->enabled = false;
		}
		this->reset();
	}

	// Methods
	float update(float velocity, float theta) {
		this->active=false;
		if (this->config.enabled == false || this->enabled == false) {
			return 0.0f;
		}

		if (this->config.v_limit != 0.0f) {
			if (std::fabs(velocity) > this->config.v_limit) {
				this->reset();
				return 0.0f;
			}
		}

		if (this->config.theta_limit != 0.0f) {
			if (std::fabs(theta) > this->config.theta_limit) {
				this->reset();
				return 0.0f;
			}
		}

		// Integrate torque directly: I_tau += ki * theta * Ts
		this->_integral_torque +=
				(this->config.ki * velocity * this->config.Ts);

		// Clamp directly in torque units
		if (this->config.max_torque > 0.0f) {
			if (this->_integral_torque > this->config.max_torque) {
				this->_integral_torque = this->config.max_torque;
			} else if (this->_integral_torque < -this->config.max_torque) {
				this->_integral_torque = -this->config.max_torque;
			}
		}
		this->active=true;
		// Output is already torque
		return this->_integral_torque;
	}

	bool is_enabled() const {
		return this->enabled;
	}

	bool is_active() const {
		return this->active && this->enabled;
	}

	void reset() {
		this->_integral_torque = 0.0f;
	}

	bilbo_vic_config_t config;
private:
	bool enabled = false;
	bool active = false;

	float _integral_torque; // stores integral in torque units
};

/* ======================================================================================== */
struct bilbo_psi_config_t {
	uint8_t enabled;
	float Ts;
	float kp;
	float ki;
	float max_torque;
};

/* ---------------------------------------------------------------------------------------- */
class BILBO_PSI_Controller {
public:
	BILBO_PSI_Controller() :
			_integral_torque(0.0f), _setpoint(0.0f), _setpoint_captured(false) {
	}

	void init(bilbo_psi_config_t config) {
		this->config = config;
		this->_integral_torque = 0.0f;
		this->_setpoint = 0.0f;
		this->_setpoint_captured = false;
		this->enabled = config.enabled;
	}

	void set_enabled(bool state) {
		if (this->enabled != state) {
			this->reset();
		}
		this->enabled = state;
	}

	void set_config(bilbo_psi_config_t config) {
		this->config = config;
		this->reset();
	}

	void set_setpoint(float psi) {
		this->_setpoint = psi;
		this->_setpoint_captured = true;
	}

	/**
	 * Update the PSI controller.
	 * Returns a DIFFERENTIAL torque: add to u_left, subtract from u_right.
	 *
	 * On the first call after enable/reset, captures the current psi as setpoint.
	 */
	float update(float psi) {
		this->active = false;
		if (this->enabled == false) {
			return 0.0f;
		}

		// Auto-capture setpoint on first update after enable
		if (!this->_setpoint_captured) {
			this->_setpoint = psi;
			this->_setpoint_captured = true;
		}

		// Compute error with angle wrapping
		float psi_error = this->_setpoint - psi;
		while (psi_error > M_PI) psi_error -= 2.0f * M_PI;
		while (psi_error < -M_PI) psi_error += 2.0f * M_PI;

		// PI control
		float p_term = this->config.kp * psi_error;
		this->_integral_torque += (this->config.ki * psi_error * this->config.Ts);

		// Clamp integral in torque units
		if (this->config.max_torque > 0.0f) {
			if (this->_integral_torque > this->config.max_torque) {
				this->_integral_torque = this->config.max_torque;
			} else if (this->_integral_torque < -this->config.max_torque) {
				this->_integral_torque = -this->config.max_torque;
			}
		}

		this->active = true;
		return p_term + this->_integral_torque;
	}

	bool is_enabled() const {
		return this->enabled;
	}

	bool is_active() const {
		return this->active && this->enabled;
	}

	void reset() {
		this->_integral_torque = 0.0f;
		this->_setpoint = 0.0f;
		this->_setpoint_captured = false;
	}

	float get_setpoint() const {
		return this->_setpoint;
	}

	bilbo_psi_config_t config;
private:
	bool enabled = false;
	bool active = false;

	float _integral_torque;
	float _setpoint;
	bool _setpoint_captured;
};

#endif /* CONTROL_BILBO_VIC_TIC_H_ */
