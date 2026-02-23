from dataclasses import dataclass
from typing import Any

@dataclass
class BaseContainer():
    config: Any
    state: Any

    
    def __getattr__(self, name):
        # expose attributes of subcontainer state
        if hasattr(self.state, name):
            return getattr(self.state, name)
        # expose attributes of subcontainer config
        if hasattr(self.config, name):
            return getattr(self.config, name)
        raise AttributeError
    
    def __setattr__(self, name: str, value: Any):
    
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





    
