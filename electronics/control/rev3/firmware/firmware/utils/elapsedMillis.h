/*
 * elapsedMillis.h
 *
 *  Created on: Jul 11, 2022
 *      Author: Dustin Lehmann
 */

#ifndef UTILS_ELAPSEDMILLIS_H_
#define UTILS_ELAPSEDMILLIS_H_

#include "stm32g0xx_hal.h"

uint32_t millis();

class elapsedMillis {
private:
	unsigned long ms;
public:
	void reset() {
		ms = millis();
	}
	elapsedMillis(void) {
		ms = millis();
	}
	elapsedMillis(unsigned long val) {
		ms = millis() - val;
	}
	elapsedMillis(const elapsedMillis &orig) {
		ms = orig.ms;
	}
	operator unsigned long() const {
		return millis() - ms;
	}
	elapsedMillis & operator =(const elapsedMillis &rhs) {
		ms = rhs.ms;
		return *this;
	}
	elapsedMillis & operator =(unsigned long val) {
		ms = millis() - val;
		return *this;
	}
	elapsedMillis & operator -=(unsigned long val) {
		ms += val;
		return *this;
	}
	elapsedMillis & operator +=(unsigned long val) {
		ms -= val;
		return *this;
	}
	elapsedMillis operator -(int val) const {
		elapsedMillis r(*this);
		r.ms += val;
		return r;
	}
	elapsedMillis operator -(unsigned int val) const {
		elapsedMillis r(*this);
		r.ms += val;
		return r;
	}
	elapsedMillis operator -(long val) const {
		elapsedMillis r(*this);
		r.ms += val;
		return r;
	}
	elapsedMillis operator -(unsigned long val) const {
		elapsedMillis r(*this);
		r.ms += val;
		return r;
	}
	elapsedMillis operator +(int val) const {
		elapsedMillis r(*this);
		r.ms -= val;
		return r;
	}
	elapsedMillis operator +(unsigned int val) const {
		elapsedMillis r(*this);
		r.ms -= val;
		return r;
	}
	elapsedMillis operator +(long val) const {
		elapsedMillis r(*this);
		r.ms -= val;
		return r;
	}
	elapsedMillis operator +(unsigned long val) const {
		elapsedMillis r(*this);
		r.ms -= val;
		return r;
	}
};



#endif /* UTILS_ELAPSEDMILLIS_H_ */
