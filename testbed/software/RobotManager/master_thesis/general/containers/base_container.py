from dataclasses import dataclass, field
from abc import abstractmethod
from typing import Any
from typing import Callable, Generic, TypeVar
T_state = TypeVar("T_state")

@dataclass
class OverarchingContainer(Generic[T_state]):
    config: ...
    state_getter: Callable[[], T_state] | None = field(default=None, repr=False, init=False)

    def set_state_getter(self, fn: Callable[[], T_state]):
        self.state_getter = fn

    @property
    def snapshot(self) -> object | None:
        if self.state_getter is None:
            return None
        return self.state_getter()
    
    # expose attributes of the sub-containers directly
    def __getattr__(self, name: str) -> Any:
        st = self.snapshot
        if st is not None and hasattr(st, name):
            return getattr(st, name)

        cfg = self.config
        if hasattr(cfg, name):
            return getattr(cfg, name)

        raise AttributeError(name)
    
    def __setattr__(self, name: str, value: Any):
        # normal fields
        if name in ("config", "state_getter"):
            super().__setattr__(name, value)
            return

        # forward to state if exists and supports update
        st = self.__dict__.get("state", None)
        if st is not None and hasattr(st, name):
            setattr(st, name, value)
            return

        # forward to config
        cfg = self.__dict__.get("config", None)
        if cfg is not None and hasattr(cfg, name):
            setattr(cfg, name, value)
            return

        # fallback
        super().__setattr__(name, value)





    
