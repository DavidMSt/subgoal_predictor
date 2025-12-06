from dataclasses import dataclass, field
from master_thesis.containers.base_container import OverarchingContainer

@dataclass(frozen=False, slots = False)
class ExecutionState:
    ...

@dataclass(frozen=True, slots=True)
class Execution_Config:
    ...

@dataclass(frozen=False, slots = False)
class ExecutionContainer(OverarchingContainer):
    config: Execution_Config = field(default_factory=Execution_Config)
    state: ExecutionState = field(default_factory=ExecutionState)