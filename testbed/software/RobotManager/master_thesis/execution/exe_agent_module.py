# 3rd party
import numpy as np
from typing import Type

# bilbolab
from core.utils.logging_utils import Logger

# master thesis
from master_thesis.containers.module_containers.exe_container import ExecutionContainer
# TODO: Apply offset bidirectional from ompl to simulation and from simulation back (initialization of start config)

class EXEAgentModule():
    exe_cont: ExecutionContainer

    def __init__(self, logger: Logger) -> None:
        self.logger = logger
        self.exe_cont = ExecutionContainer()
