# # signature_check.py
# from __future__ import annotations
# import inspect
# from typing import Any, Callable, Iterable, Mapping, Union
#
# def _unwrap(cb: Any) -> Callable:
#     """If it's a Callback, unwrap to the underlying function."""
#     fn = getattr(cb, "function", None)
#     if callable(fn):
#         return fn
#     if callable(cb):
#         return cb
#     raise TypeError("Object is neither callable nor a Callback-like object")
#
#
# def check_signature(
#     func_or_cb: Any,
#     *,
#     # Check the function has these argument names (positional or keyword)
#     arg_names: Iterable[str] | None = None,
#
#     # Check the function can accept these **keyword** names
#     kwarg_names: Iterable[str] | None = None,
#
#     # Check expected types for arguments at call-time
#     arg_types: Mapping[str, type] | None = None,
#
#     # If true: require the arguments in arg_names to be keyword-only (prefer safety)
#     require_keyword_only: bool = False,
#
#     # Check return type based on a sample call (optional)
#     return_type: type | None = None,
#
#     # Sample inputs to test runtime type behavior (optional)
#     test_call_kwargs: Mapping[str, Any] | None = None,
#
# ) -> None:
#     """
#     Raises TypeError with a helpful message if checks fail.
#     Returns None if everything passes.
#     """
#     fn = _unwrap(func_or_cb)
#     sig = inspect.signature(fn)
#     params = sig.parameters
#
#     # ---------------------------------------------------------
#     # 1) Check argument *names*
#     # ---------------------------------------------------------
#     if arg_names:
#         for name in arg_names:
#             if name not in params:
#                 raise TypeError(
#                     f"Expected argument '{name}' not found in function {fn.__name__}."
#                 )
#
#     # ---------------------------------------------------------
#     # 2) Check keyword acceptance
#     # ---------------------------------------------------------
#     if kwarg_names:
#         has_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
#         for name in kwarg_names:
#             if name not in params and not has_kwargs:
#                 raise TypeError(
#                     f"Function {fn.__name__} must accept keyword '{name}' (explicitly or via **kwargs)."
#                 )
#
#     # ---------------------------------------------------------
#     # 3) Keyword-only requirement (safety)
#     # ---------------------------------------------------------
#     if require_keyword_only and arg_names:
#         for name in arg_names:
#             p = params[name]
#             if p.kind not in (inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.VAR_KEYWORD):
#                 raise TypeError(
#                     f"Argument '{name}' must be keyword-only (enforce with *, or **kwargs)."
#                 )
#
#     # ---------------------------------------------------------
#     # 4) Optional runtime type check
#     # ---------------------------------------------------------
#     if arg_types:
#         # Only verifying annotations — optional
#         for name, expected_type in arg_types.items():
#             ann = params[name].annotation
#             if ann is inspect._empty:
#                 continue  # no annotation provided
#             try:
#                 if not issubclass(expected_type, ann) and not issubclass(ann, expected_type):
#                     raise TypeError(
#                         f"Argument '{name}' has incompatible annotation {ann}, expected {expected_type}."
#                     )
#             except TypeError:
#                 pass  # fallback: skip exotic things
#
#     # ---------------------------------------------------------
#     # 5) Optional runtime CALL test
#     # ---------------------------------------------------------
#     if test_call_kwargs:
#         result = fn(**test_call_kwargs)
#         if return_type is not None and not isinstance(result, return_type):
#             raise TypeError(
#                 f"Function returned {type(result)}, expected {return_type}."
#             )
#
#
# # -------------------------------------------------------------------------
# # Convenience wrapper: short and sweet
# # -------------------------------------------------------------------------
# def must_accept(fn_or_cb, *names: str) -> None:
#     """Quick check: assert all names are valid keyword params."""
#     check_signature(fn_or_cb, kwarg_names=names)


# signature_check.py
from __future__ import annotations
import inspect
from typing import Any, Callable, Iterable, Mapping


class SignatureCheckError(TypeError):
    """
    TypeError subclass that carries rich context about the function
    that failed signature checks (module, qualname, file, line).
    """

    def __init__(self, message: str, fn: Callable):
        self.fn = fn
        self.module = getattr(fn, "__module__", None)
        self.qualname = getattr(fn, "__qualname__", getattr(fn, "__name__", repr(fn)))
        # File and line can be missing for builtins or C-extensions
        filename = None
        lineno = None
        try:
            filename = inspect.getsourcefile(fn) or inspect.getfile(fn)
        except Exception:
            # As a fallback, try the module file
            try:
                mod = inspect.getmodule(fn)
                filename = getattr(mod, "__file__", None)
            except Exception:
                pass
        try:
            # getsourcelines returns (list_of_lines, start_line_number)
            _, lineno = inspect.getsourcelines(fn)
        except Exception:
            lineno = None

        self.filename = filename
        self.lineno = lineno

        context_bits = []
        if self.module:
            context_bits.append(self.module)
        if self.qualname:
            # join with a dot only if module present
            if context_bits:
                context_bits[-1] = f"{context_bits[-1]}.{self.qualname}"
            else:
                context_bits.append(self.qualname)
        loc = None
        if self.filename and self.lineno:
            loc = f"{self.filename}:{self.lineno}"
        elif self.filename:
            loc = f"{self.filename}"

        ctx = ""
        if context_bits or loc:
            left = context_bits[0] if context_bits else ""
            if loc:
                ctx = f" [in {left} @ {loc}]" if left else f" [in {loc}]"
            else:
                ctx = f" [in {left}]"

        super().__init__(f"{message}{ctx}")


def _unwrap(cb: Any) -> Callable:
    """
    If it's a Callback-like (has a .function attr that is callable),
    unwrap to the underlying function, else return the callable itself.
    """
    fn = getattr(cb, "function", None)
    if callable(fn):
        return fn
    if callable(cb):
        return cb
    raise TypeError("Object is neither callable nor a Callback-like object")


def check_signature(
        func_or_cb: Any,
        *,
        # Check the function has these argument names (positional or keyword)
        arg_names: Iterable[str] | None = None,

        # Check the function can accept these **keyword** names
        kwarg_names: Iterable[str] | None = None,

        # Check expected types for arguments at call-time
        arg_types: Mapping[str, type] | None = None,

        # If true: require the arguments in arg_names to be keyword-only (prefer safety)
        require_keyword_only: bool = False,

        # Check return type based on a sample call (optional)
        return_type: type | None = None,

        # Sample inputs to test runtime type behavior (optional)
        test_call_kwargs: Mapping[str, Any] | None = None,

) -> None:
    """
    Raises SignatureCheckError (a TypeError) with a helpful message if checks fail.
    Returns None if everything passes.
    """
    fn = _unwrap(func_or_cb)
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError) as e:
        # Some callables (e.g., builtins) may not have a retrievable signature
        raise SignatureCheckError(f"Unable to inspect signature: {e}", fn) from e

    params = sig.parameters

    # ---------------------------------------------------------
    # 1) Check argument *names*
    # ---------------------------------------------------------
    if arg_names:
        for name in arg_names:
            if name not in params:
                raise SignatureCheckError(
                    f"Expected argument '{name}' not found in function {getattr(fn, '__name__', '<callable>')}.",
                    fn,
                )

    # ---------------------------------------------------------
    # 2) Check keyword acceptance
    # ---------------------------------------------------------
    if kwarg_names:
        has_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
        for name in kwarg_names:
            if name not in params and not has_kwargs:
                raise SignatureCheckError(
                    f"Function {getattr(fn, '__name__', '<callable>')} must accept keyword '{name}' (explicitly or via **kwargs).",
                    fn,
                )

    # ---------------------------------------------------------
    # 3) Keyword-only requirement (safety)
    # ---------------------------------------------------------
    if require_keyword_only and arg_names:
        for name in arg_names:
            # name presence guaranteed by step (1)
            p = params[name]
            if p.kind not in (inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.VAR_KEYWORD):
                raise SignatureCheckError(
                    f"Argument '{name}' must be keyword-only (enforce with *, or **kwargs).",
                    fn,
                )

    # ---------------------------------------------------------
    # 4) Optional annotation/type compatibility check
    # ---------------------------------------------------------
    if arg_types:
        for name, expected_type in arg_types.items():
            if name not in params:
                raise SignatureCheckError(
                    f"Type check requested for unknown parameter '{name}'.",
                    fn,
                )
            ann = params[name].annotation
            if ann is inspect._empty:
                # No annotation provided; skip strictness
                continue
            try:
                # Be forgiving: allow either direction of subclassing to count as compatible
                if not (isinstance(ann, type) and isinstance(expected_type, type)):
                    # Exotic annotations (typing constructs) are skipped
                    continue
                if not (issubclass(expected_type, ann) or issubclass(ann, expected_type)):
                    raise SignatureCheckError(
                        f"Argument '{name}' has incompatible annotation {ann!r}, expected {expected_type!r}.",
                        fn,
                    )
            except TypeError:
                # Skip exotic/parameterized generics, Protocols, etc.
                continue

    # ---------------------------------------------------------
    # 5) Optional runtime CALL test
    # ---------------------------------------------------------
    if test_call_kwargs:
        try:
            result = fn(**test_call_kwargs)
        except Exception as e:
            # Surface the original error but attach function context
            raise SignatureCheckError(
                f"Test call with kwargs {dict(test_call_kwargs)!r} raised {e.__class__.__name__}: {e}",
                fn,
            ) from e

        if return_type is not None and not isinstance(result, return_type):
            raise SignatureCheckError(
                f"Function returned {type(result)!r}, expected {return_type!r}.",
                fn,
            )


# -------------------------------------------------------------------------
# Convenience wrapper: short and sweet
# -------------------------------------------------------------------------
def must_accept(fn_or_cb, *names: str) -> None:
    """Quick check: assert all names are valid keyword params (or **kwargs is present)."""
    check_signature(fn_or_cb, kwarg_names=names)
