from __future__ import annotations  # Optional, works either way
import inspect
import typing
from typing import get_origin, get_args, Any

# Constants to indicate whether a parameter is required or optional.
REQUIRED = True
OPTIONAL = False


def _is_union(t) -> bool:
    # Supports PEP 604 (X | Y) and typing.Union
    return get_origin(t) is typing.Union or str(type(t)) == "<class 'types.UnionType'>"


def _none_type():
    return type(None)


def _type_matches(value, expected_type) -> bool:
    """
    Runtime type check that understands:
      - Unions (including Optional)
      - Plain classes (int, float, str, ...)
      - typing.Any (always passes)
    """
    if expected_type is Any:
        return True

    origin = get_origin(expected_type)

    # Handle Union / X | Y (including Optional)
    if _is_union(expected_type):
        return any(_type_matches(value, arg) for arg in get_args(expected_type))

    # typing.Optional[T] is Union[T, NoneType]; handled above

    # typing.Literal, etc. — keep it simple: fall back to isinstance on origin if present
    if origin is not None:
        try:
            return isinstance(value, origin)
        except TypeError:
            # For exotic typing constructs we conservatively skip strict checking
            return True

    # Plain class/type
    try:
        return isinstance(value, expected_type)
    except TypeError:
        # If expected_type isn't a real type (rare), skip strict checking
        return True


class Callback:
    inputs: dict
    lambdas: dict
    parameters: dict
    function: typing.Callable
    once: bool
    discard_inputs: bool
    container: CallbackContainer | None

    # ------------------------------------------------------------------------------------------------------------------
    def __init__(self,
                 function: typing.Callable,
                 inputs: dict = None,
                 lambdas: dict = None,
                 parameters: dict = None,
                 discard_inputs: bool = False,
                 once: bool = False,
                 *args, **kwargs):
        self.function = function

        self.inputs = inputs or {}
        self.lambdas = lambdas or {}
        self.parameters = parameters or {}
        self.discard_inputs = discard_inputs
        self.once = once
        self.container = None

    # ------------------------------------------------------------------------------------------------------------------
    def __call__(self, *args, **kwargs):
        # Prepare any lazy values
        lambdas_exec = {key: value() for (key, value) in self.lambdas.items()}

        # If we've been marked "once", remove ourselves after a successful call
        if self.once and self.container is not None:
            self.container.remove(self)

        # Compose call kwargs
        if self.discard_inputs:
            # Discard external args/kwargs entirely; still allow explicitly attached inputs/lambdas if present.
            call_args = ()
            call_kwargs = {**self.inputs, **lambdas_exec}
        else:
            call_args = args
            call_kwargs = {**self.inputs, **kwargs, **lambdas_exec}

        ret = self.function(*call_args, **call_kwargs)

        # Optional return type validation (only if container asked for it)
        if self.container is not None and self.container.expected_return is not None:
            expected_ret = self.container.expected_return
            # Only check when there actually is a value, or when the expected type is not strictly NoneType
            if ret is not None or (get_origin(expected_ret) is not typing.Type and expected_ret is not _none_type()):
                if not _type_matches(ret, expected_ret):
                    exp_txt = getattr(expected_ret, "__name__", str(expected_ret))
                    got_txt = type(ret).__name__ if ret is not None else "NoneType"
                    raise TypeError(f"Callback returned type {got_txt}, expected {exp_txt}.")

        return ret


class CallbackContainer:
    callbacks: list[Callback]

    # ------------------------------------------------------------------------------------------------------------------
    def __init__(self, inputs: list[tuple | str] | None = None, parameters=None, returns: typing.Any | None = None):
        """
        inputs:
          - None => no signature/type checking for inputs (backward compatible).
          - List entries can be:
              'name'                             -> shorthand for ('name', Any, REQUIRED)
              ('name', type)                     -> required parameter of given type
              ('name', type, REQUIRED/OPTIONAL)  -> explicit required flag
        parameters:
          - Backward-compatible parameter spec (list of (name, type, bool)) validated at registration-time
            against the 'parameters' dict passed to .register(...).
        returns:
          - Optional return type to validate against when callbacks are invoked. If None, no return check.
        """
        self.callbacks = []
        self.parameters = parameters
        self.expected_return = returns

        # ---- Parse the "parameters" schema (existing feature) --------------------------------------------
        if parameters is not None:
            if not isinstance(parameters, list):
                raise ValueError("Parameters must be provided as a list of tuples.")
            expected = {}
            for param_spec in parameters:
                if not (isinstance(param_spec, tuple) and len(param_spec) == 3):
                    raise ValueError("Each parameter specification must be a tuple of (str, type, bool).")
                name, expected_type, required_flag = param_spec
                if not isinstance(name, str):
                    raise ValueError("Parameter name must be a string.")
                if not isinstance(required_flag, bool):
                    raise ValueError("Parameter required flag must be a boolean.")
                if not isinstance(expected_type, type) and not _is_union(expected_type) and expected_type is not Any:
                    raise ValueError("Parameter expected type must be a type or typing.Union/Any.")
                expected[name] = (expected_type, required_flag)
            self.expected_parameters = expected
        else:
            self.expected_parameters = {}

        # ---- Parse the new "inputs" schema (function input spec) -----------------------------------------
        if inputs is not None:
            if not isinstance(inputs, list):
                raise ValueError("inputs must be provided as a list of tuples/strings.")
            expected_inputs: dict[str, tuple[typing.Any, bool]] = {}
            for spec in inputs:
                # Allow shorthand: 'name' => (name, Any, REQUIRED)
                if isinstance(spec, str):
                    name = spec
                    expected_type = Any
                    required_flag = True
                elif isinstance(spec, tuple) and len(spec) in (2, 3):
                    if len(spec) == 2:
                        name, expected_type = spec
                        required_flag = True
                    else:
                        name, expected_type, required_flag = spec
                    if not isinstance(name, str):
                        raise ValueError("Input name must be a string.")
                    if not isinstance(required_flag, bool):
                        raise ValueError("Input required flag must be a boolean.")
                    # type may be real type or Union/Any
                    if not (isinstance(expected_type, type) or _is_union(expected_type) or expected_type is Any):
                        raise ValueError("Input expected type must be a type or typing.Union/Any.")
                else:
                    raise ValueError("Each inputs item must be 'name', ('name', type), or ('name', type, bool).")
                expected_inputs[name] = (expected_type, required_flag)
            self.expected_inputs = expected_inputs
        else:
            self.expected_inputs = {}

    # ---------- cloning support (used by decorator to avoid shared containers) ----------------------------
    def clone_schema(self) -> "CallbackContainer":
        """
        Create a new, empty container with the same schema/return-type, but without any registered callbacks.
        """
        cloned = CallbackContainer()
        cloned.expected_inputs = dict(getattr(self, "expected_inputs", {}))
        cloned.expected_parameters = dict(getattr(self, "expected_parameters", {}))
        cloned.expected_return = getattr(self, "expected_return", None)
        # callbacks intentionally left empty
        return cloned

    # ------------------------------------------------------------------------------------------------------------------
    def _validate_parameters_payload(self, parameters: dict | None) -> dict:
        if not self.expected_parameters:
            return parameters or {}
        if parameters is None:
            parameters = {}
        for param_name, (expected_type, required_flag) in self.expected_parameters.items():
            if param_name not in parameters:
                if required_flag:
                    raise RuntimeError(f"Missing required parameter: {param_name}")
                else:
                    parameters[param_name] = None
            else:
                if parameters[param_name] is not None and not _type_matches(parameters[param_name], expected_type):
                    exp_txt = getattr(expected_type, "__name__", str(expected_type))
                    got_txt = type(parameters[param_name]).__name__
                    raise TypeError(
                        f"Parameter '{param_name}' is expected to be of type {exp_txt}, got {got_txt}."
                    )
        return parameters

    # ------------------------------------------------------------------------------------------------------------------
    def _validate_function_accepts_inputs(self, function: typing.Callable, discard_inputs: bool):
        """
        If input spec exists and we're NOT discarding inputs, ensure the function can accept the named inputs.
        We don't force type annotations on the function; type correctness is enforced at call-time.
        """
        if not self.expected_inputs or discard_inputs:
            return

        sig = inspect.signature(function)
        params = sig.parameters
        accepts_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())

        for name in self.expected_inputs.keys():
            if name in params:
                continue
            if not accepts_kwargs:
                raise TypeError(
                    f"Registered callback must accept an argument named '{name}' (or use **kwargs)."
                )

    # ------------------------------------------------------------------------------------------------------------------
    def register(self,
                 function: typing.Callable,
                 inputs: dict = None,
                 parameters: dict = None,
                 lambdas: dict = None,
                 discard_inputs: bool = False,
                 once: bool = False,
                 *args, **kwargs):
        # Validate the legacy "parameters" payload if a schema was provided
        parameters = self._validate_parameters_payload(parameters)

        # If we have an input schema, ensure the function can accept the named inputs (unless discarding)
        self._validate_function_accepts_inputs(function, discard_inputs)

        callback = Callback(function, inputs=inputs, lambdas=lambdas, parameters=parameters,
                            discard_inputs=discard_inputs, once=once, *args, **kwargs)
        self.callbacks.append(callback)
        callback.container = self
        return callback

    # ------------------------------------------------------------------------------------------------------------------
    def remove(self, callback):
        if isinstance(callback, Callback):
            if callback in self.callbacks:
                self.callbacks.remove(callback)
        elif callable(callback):
            cb = next((cb for cb in self.callbacks if cb.function == callback), None)
            if cb is not None:
                self.callbacks.remove(cb)

    # ------------------------------------------------------------------------------------------------------------------
    def _validate_call_inputs(self, provided_kwargs: dict):
        """
        Validate types for inputs passed to .call(...).
        If the user doesn't pass any inputs (kwargs empty), we skip validation, matching the requested behavior.
        """
        if not self.expected_inputs:
            return  # no schema => no checks
        if not provided_kwargs:
            return  # "If no inputs are given, then it should just not check inputs"

        for name, (expected_type, required_flag) in self.expected_inputs.items():
            if name not in provided_kwargs:
                if required_flag:
                    raise TypeError(f"Missing required input '{name}' when invoking callbacks.")
                else:
                    continue
            val = provided_kwargs[name]
            # Allow None only if Optional[...] (i.e., Union[..., NoneType]) or expected_type is Any
            if val is None:
                if expected_type is Any:
                    continue
                if _is_union(expected_type) and _none_type() in get_args(expected_type):
                    continue
                # Not optional
                raise TypeError(f"Input '{name}' cannot be None.")
            if not _type_matches(val, expected_type):
                exp_txt = getattr(expected_type, "__name__", str(expected_type))
                got_txt = type(val).__name__
                raise TypeError(f"Input '{name}' expected type {exp_txt}, got {got_txt}.")

    # ------------------------------------------------------------------------------------------------------------------
    def call(self, *args, **kwargs):
        # Validate provided kwargs against the container's input schema
        self._validate_call_inputs(kwargs)

        for callback in list(self.callbacks):  # snapshot to tolerate self-removal
            callback(*args, **kwargs)

    # ------------------------------------------------------------------------------------------------------------------
    def __iter__(self):
        return iter(self.callbacks)

    # ------------------------------------------------------------------------------------------------------------------
    def clear_callbacks(self):
        self.callbacks.clear()


def callback_definition(cls):
    """
    Class decorator: for every annotated attribute whose annotation is (or derives from) CallbackContainer,
    ensure an instance exists on the instance after __init__.

    - If the class provides a default CallbackContainer instance, we CLONE its schema per instance to avoid
      shared callback lists (which cause cross-talk and loops).
    - If no default present, we create a default empty CallbackContainer().
    """
    original_init = getattr(cls, "__init__", None)

    def new_init(self, *args, **kwargs):
        resolved_annotations = typing.get_type_hints(cls)
        for name, annotation in resolved_annotations.items():
            if isinstance(annotation, type) and issubclass(annotation, CallbackContainer):
                # What's currently on the instance?
                current_val = getattr(self, name, None)
                # Is there a class-level default?
                class_default = getattr(cls, name, None)

                if isinstance(class_default, CallbackContainer):
                    # If instance doesn't already override it OR still points at the class default,
                    # replace with a per-instance clone of the schema.
                    if current_val is None or current_val is class_default:
                        setattr(self, name, class_default.clone_schema())
                else:
                    # No class default: create a fresh empty container if missing
                    if current_val is None:
                        setattr(self, name, CallbackContainer())
        if original_init:
            original_init(self, *args, **kwargs)

    cls.__init__ = new_init
    return cls


class CallbackGroup:
    def clearAllCallbacks(self):
        resolved_annotations = typing.get_type_hints(self.__class__)
        for name, annotation in resolved_annotations.items():
            attr = getattr(self, name, None)
            if isinstance(attr, CallbackContainer):
                attr.clear_callbacks()


# ------------------------------- Demo & backwards compatibility checks ------------------------------------
@callback_definition
class CallbacksA(CallbackGroup):
    callback1: CallbackContainer
    callback2: CallbackContainer


if __name__ == "__main__":
    # Example using input specs & return type checks ----------------
    class SubscriberMatch:  # minimal stub for the demo
        ...


    @callback_definition
    class RobotCallbacks:
        # Accept either the shorthand names or typed tuples
        finished: CallbackContainer = CallbackContainer(
            inputs=[('data', str), ('match', dict)],
            returns=None
        )


    def callback_function(data: float, match=None):
        print("Callback function called:", data)


    # Register a callback with a typed spec
    robot_cb = RobotCallbacks()
    robot_cb.finished.register(callback_function)

    # Call-time: types are checked for typed specs only; name presence enforced by registration step.
    robot_cb.finished.call(data="x", match={})  # OK (string is allowed by spec above)
