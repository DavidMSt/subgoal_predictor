/*
 * core_utils_functionpointer.h
 *
 *  Created on: 23 Feb 2023
 *      Author: lehmann_workstation
 */

#ifndef UTILS_CORE_UTILS_FUNCTIONPOINTER_H_
#define UTILS_CORE_UTILS_FUNCTIONPOINTER_H_

/*
 * FunctionPointer.hpp
 *
 *  Created on: 25.03.2018
 *      Author: Dustin
 */

#ifndef F4_FUNCTIONPOINTER_HPP_
#define F4_FUNCTIONPOINTER_HPP_

#include <string.h>
#include <stdint.h>

#define MBED_OPERATORS

template <typename R, typename A1>
class core_utils_FunctionPointer{
public:
    /** Create a FunctionPointer, attaching a static function
     *
     *  @param function The static function to attach (default is none)
     */
	core_utils_FunctionPointer(R (*function)(A1) = 0) {
        attach(function);
    }

    /** Create a FunctionPointer, attaching a member function
     *
     *  @param object The object pointer to invoke the member function on (i.e. the this pointer)
     *  @param function The address of the member function to attach
     */
    template<typename T>
    core_utils_FunctionPointer(T *object, R (T::*member)(A1)) {
        attach(object, member);
    }

    /** Attach a static function
     *
     *  @param function The static function to attach (default is none)
     */
    void attach(R (*function)(A1)) {
        _p.function = function;
        _membercaller = 0;
    }

    /** Attach a member function
     *
     *  @param object The object pointer to invoke the member function on (i.e. the this pointer)
     *  @param function The address of the member function to attach
     */
    template<typename T>
    void attach(T *object, R (T::*member)(A1)) {
        _p.object = static_cast<void*>(object);
        *reinterpret_cast<R (T::**)(A1)>(_member) = member;
        _membercaller = &core_utils_FunctionPointer::membercaller<T>;
    }

    /** Call the attached static or member function
     */
    R call(A1 a) {
        if (_membercaller == 0 && _p.function) {
           return _p.function(a);
        } else if (_membercaller && _p.object) {
           return _membercaller(_p.object, _member, a);
        } else {
        }
        return R();
    }

    /** Get registered static function
     */
    R(*get_function(A1))() {
        return _membercaller ? (R(*)(A1))0 : (R(*)(A1))_p.function;
    }

#ifdef MBED_OPERATORS
    R operator ()(A1 a) {
        return call(a);
    }
    operator bool(void) const {
        return (_membercaller != NULL ? _p.object : (void*)_p.function) != NULL;
    }
#endif
private:
    template<typename T>
    static R membercaller(void *object, uintptr_t *member, A1 a) {
        T* o = static_cast<T*>(object);
        R (T::**m)(A1) = reinterpret_cast<R (T::**)(A1)>(member);
        return (o->**m)(a);
    }

    union {
        R (*function)(A1); // static function pointer
        void *object;      // object this pointer
    } _p;
    uintptr_t _member[4]; // aligned raw member function pointer storage - converted back by registered _membercaller
    R (*_membercaller)(void*, uintptr_t*, A1); // registered membercaller function to convert back and call _m.member on _object
};

/** A class for storing and calling a pointer to a static or member function (R ()(void))
 */
template <typename R>
class core_utils_FunctionPointer<R, void>{
public:
    /** Create a FunctionPointer, attaching a static function
     *
     *  @param function The static function to attach (default is none)
     */
	core_utils_FunctionPointer(R (*function)(void) = 0) {
        attach(function);
    }

    /** Create a FunctionPointer, attaching a member function
     *
     *  @param object The object pointer to invoke the member function on (i.e. the this pointer)
     *  @param function The address of the void member function to attach
     */
    template<typename T>
    core_utils_FunctionPointer(T *object, R (T::*member)(void)) {
        attach(object, member);
    }

    /** Attach a static function
     *
     *  @param function The void static function to attach (default is none)
     */
    void attach(R (*function)(void)) {
        _p.function = function;
        _membercaller = 0;
    }

    /** Attach a member function
     *
     *  @param object The object pointer to invoke the member function on (i.e. the this pointer)
     *  @param function The address of the void member function to attach
     */
    template<typename T>
    void attach(T *object, R (T::*member)(void)) {
        _p.object = static_cast<void*>(object);
        *reinterpret_cast<R (T::**)(void)>(_member) = member;
        _membercaller = &core_utils_FunctionPointer::membercaller<T>;
    }

    /** Call the attached static or member function
     */
    R call(){
        if (_membercaller == 0 && _p.function) {
            return _p.function();
        } else if (_membercaller && _p.object) {
            return _membercaller(_p.object, _member);
        }
        return R();
//        return (R)0;
    }

    /** Get registered static function
     */
    R(*get_function())() {
        return _membercaller ? (R(*)())0 : (R(*)())_p.function;
    }

#ifdef MBED_OPERATORS
    R operator ()(void) {
        return call();
    }
    operator bool(void) const {
        return (_membercaller != NULL ? _p.object : (void*)_p.function) != NULL;
    }
#endif

private:
    template<typename T>
    static R membercaller(void *object, uintptr_t *member) {
        T* o = static_cast<T*>(object);
        R (T::**m)(void) = reinterpret_cast<R (T::**)(void)>(member);
        return (o->**m)();
    }

    union {
        R (*function)(void); // static function pointer
        void *object;        // object this pointer
    } _p;
    uintptr_t _member[4]; // aligned raw member function pointer storage - converted back by registered _membercaller
    R (*_membercaller)(void*, uintptr_t*); // registered membercaller function to convert back and call _m.member on _object
};

//typedef FunctionPointerArg1<void, void*> FunctionPointer;
//typedef FunctionPointerArg1<void, int> event_callback_t;

#endif /* F4_FUNCTIONPOINTER_HPP_ */




#endif /* UTILS_CORE_UTILS_FUNCTIONPOINTER_H_ */
