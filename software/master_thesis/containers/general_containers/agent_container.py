from dataclasses import dataclass, field
from robots.frodo.simulation.frodo import FRODO_State
from master_thesis.containers.base_container import BaseContainer
from robots.frodo.simulation.frodo import FRODO_State

@dataclass
class FRODO_AgentState(FRODO_State):
    # buffer for incoming communication from other agents
    comm_buffer: dict = field(default_factory=dict)

@dataclass(frozen=True, slots = True)
class FRODO_Agent_Config:
    color: tuple[float, float, float] = (1.0, 1.0, 1.0)
    length: float = 0.157
    width: float = 0.115
    height: float = 0.11
    Ts: float | None = None # gets overwritten with sim Ts once agent is created

@dataclass(frozen=False, slots=False)
class FRODOAgentContainer(BaseContainer):
    agent_id: str = field(kw_only=True)
    config: FRODO_Agent_Config = field(default_factory=FRODO_Agent_Config)
    state: FRODO_AgentState = field(default_factory= lambda: FRODO_AgentState(0.0,0.0,0.0,0.0,0.0))




