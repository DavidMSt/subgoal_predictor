from dataclasses import dataclass
from extensions.simulation.src.objects.frodo.frodo import FRODO_State
from master_thesis.general.containers.base_container import OverarchingContainer

@dataclass(frozen=True, slots = True)
class FRODO_Agent_Config:
    color: tuple[float, float, float] = (1.0, 1.0, 1.0)
    length: float = 0.157
    width: float = 0.115
    height: float = 0.11
    Ts: float | None = None # gets overwritten with sim Ts once agent is created

@dataclass(frozen = False, slots = False)
class FRODO_Agent_State:
    x: float = 0.0
    y: float = 0.0
    psi: float = 0.0

@dataclass(frozen=False, slots=False)
class FRODOAgentContainer(OverarchingContainer):
    config: FRODO_Agent_Config
    sim_agent: object

    @property
    def state(self) -> FRODO_Agent_State:
        cfg = self.sim_agent.configuration_global
        pos = cfg['pos']
        psi = cfg['ori'][0] if 'ori' in cfg else 0.0
        return FRODO_Agent_State(x=pos[0], y=pos[1], psi=psi)