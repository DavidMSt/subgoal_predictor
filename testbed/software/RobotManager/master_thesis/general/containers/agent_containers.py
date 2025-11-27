from dataclasses import dataclass
from extensions.simulation.src.objects.frodo.frodo import FRODO_State
from master_thesis.general.containers.base_container import OverarchingContainer
from extensions.simulation.src.objects.frodo.frodo import FRODO_State
from typing import Callable

@dataclass(frozen=True, slots = True)
class FRODO_Agent_Config:
    color: tuple[float, float, float] = (1.0, 1.0, 1.0)
    length: float = 0.157
    width: float = 0.115
    height: float = 0.11
    Ts: float | None = None # gets overwritten with sim Ts once agent is created

@dataclass(frozen=False, slots=False)
class FRODOAgentContainer(OverarchingContainer):
    config: FRODO_Agent_Config
    state_getter: Callable[[], FRODO_State]

    @property
    def snapshot(self) -> FRODO_State:
        return self.state_getter()