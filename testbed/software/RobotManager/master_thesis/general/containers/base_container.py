from dataclasses import dataclass
from abc import abstractmethod
from typing import Any

@dataclass
class OverarchingContainer:
    config: ...
    state: ...
    
    # expose attributes of the sub-containers directly
    def __getattr__(self, name: str) -> Any:
        if hasattr(self, "state") and hasattr(self.state, name):
            return getattr(self.state, name)
        
        elif hasattr(self, "config") and hasattr(self.config, name):
            return getattr(self.config, name)

        raise AttributeError(name)






    
