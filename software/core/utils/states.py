import dataclasses
from typing import Type, TypeVar, Any, Iterable, Union
import numpy as np

T = TypeVar("T", bound="State")


class State:
    """
    Base class: any subclass becomes a dataclass automatically and
    gets asarray()/fromarray()/as_state() methods that IDEs can see.
    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        dc_kwargs = getattr(cls, "__state_dataclass_kwargs__", {})
        if not dataclasses.is_dataclass(cls):
            dataclasses.dataclass(cls, **dc_kwargs)

    # ---------------- convenience methods ----------------

    def asarray(self) -> np.ndarray:
        """Return dataclass fields as a 1D float NumPy array in field order."""
        return np.asarray(dataclasses.astuple(self), dtype=float)

    @classmethod
    def fromarray(cls: Type[T], arr: Iterable[Any]) -> T:
        """Build an instance from a sequence/array in the same field order."""
        arr = np.asarray(arr, dtype=float)
        fields = [f.name for f in dataclasses.fields(cls)]
        if arr.ndim != 1:
            raise ValueError("fromarray expects a 1D array/sequence")
        if len(arr) != len(fields):
            raise ValueError(f"Expected {len(fields)} elements, got {len(arr)}")
        return cls(*arr)  # type: ignore[misc]

    @classmethod
    def as_state(cls: Type[T], value: Union[T, float, Iterable[Any], np.ndarray]) -> T:
        """
        Convert various inputs into a State instance of this class:
          - same-class instance → returned unchanged
          - numpy array/list/tuple → fromarray
          - float → only allowed if the class has exactly one field
        """
        if isinstance(value, cls):
            return value
        elif isinstance(value, (list, tuple, np.ndarray)):
            return cls.fromarray(value)
        elif isinstance(value, (int, float)):
            fields = [f.name for f in dataclasses.fields(cls)]
            if len(fields) != 1:
                raise ValueError(
                    f"Cannot build {cls.__name__} from a single float: "
                    f"class has {len(fields)} fields"
                )
            return cls(value)  # type: ignore
        else:
            raise TypeError(f"Cannot convert {type(value)} to {cls.__name__}")


def is_state_dataclass(cls):
    """Check if a class is a dataclass that inherits from State."""
    return dataclasses.is_dataclass(cls) and issubclass(cls, State)


def listToStateList(data, state_dataclass: type[State]):
    """Convert a list of dataclass instances to a list of State instances."""
    if not is_state_dataclass(state_dataclass):
        raise ValueError("state_dataclass must be a dataclass that inherits from State")
    return [state_dataclass.as_state(d) for d in data]


def vectorToStateList(data, state_dataclass: type[State]):
    """Convert a 1D NumPy array to a list of State instances."""
    if not is_state_dataclass(state_dataclass):
        raise ValueError("state_dataclass must be a dataclass that inherits from State")

    data = list(data)
    return [state_dataclass.as_state(d) for d in data]
