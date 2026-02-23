import dataclasses

import numpy as np

from core.utils.colors import NamedColor, Colors
from core.utils.files import get_absolute_path

# ======================================================================================================================
EXPERIMENT_DIR = get_absolute_path("./experiments")
PLANS_DIR = get_absolute_path("./experiments/utilities/plans")


# ======================================================================================================================
@dataclasses.dataclass
class SimulatedAgentDefinition:
    id: str
    color: list | tuple
    fov: float = np.deg2rad(100)
    size = 0.2
    vision_radius: float = 1.5


# SIMULATED_AGENTS = [
#     SimulatedAgentDefinition("vfrodo1", Colors.lime),
#     SimulatedAgentDefinition("vfrodo2", Colors.aquamarine),
#     SimulatedAgentDefinition("vfrodo3", Colors.orange),
#     SimulatedAgentDefinition("vfrodo4", Colors.coral),
#     SimulatedAgentDefinition("vfrodo5", Colors.lightpurple),
# ]

SIMULATED_AGENTS = [
    SimulatedAgentDefinition("vfrodo1", Colors.lime),
    SimulatedAgentDefinition("vfrodo2", Colors.aquamarine),
    SimulatedAgentDefinition("vfrodo3", Colors.orange),
    SimulatedAgentDefinition("vfrodo4", Colors.coral),
    SimulatedAgentDefinition("vfrodo5", Colors.lightpurple),
    SimulatedAgentDefinition("vfrodo6", Colors.blue),
    SimulatedAgentDefinition("vfrodo7", Colors.crimson),
    SimulatedAgentDefinition("vfrodo8", Colors.teal),
    SimulatedAgentDefinition("vfrodo9", Colors.gold),
    SimulatedAgentDefinition("vfrodo10", Colors.emerald),
    SimulatedAgentDefinition("vfrodo11", Colors.sky),
    SimulatedAgentDefinition("vfrodo12", Colors.darkorange),
    SimulatedAgentDefinition("vfrodo13", Colors.royalblue),
    SimulatedAgentDefinition("vfrodo14", Colors.turquoise),
    SimulatedAgentDefinition("vfrodo15", Colors.chocolate),
    SimulatedAgentDefinition("vfrodo16", Colors.magenta),
    SimulatedAgentDefinition("vfrodo17", Colors.forest),
    SimulatedAgentDefinition("vfrodo18", Colors.cyan),
    SimulatedAgentDefinition("vfrodo19", Colors.plum),
    SimulatedAgentDefinition("vfrodo20", Colors.navy),
    SimulatedAgentDefinition("vfrodo21", Colors.indigo),
    SimulatedAgentDefinition("vfrodo22", Colors.tan),
    SimulatedAgentDefinition("vfrodo23", Colors.jade),
    SimulatedAgentDefinition("vfrodo24", Colors.mint),
    SimulatedAgentDefinition("vfrodo25", Colors.deepsky),
    SimulatedAgentDefinition("vfrodo26", Colors.dodgerblue),
    SimulatedAgentDefinition("vfrodo27", Colors.lightgreen),
    SimulatedAgentDefinition("vfrodo28", Colors.orchid),
    SimulatedAgentDefinition("vfrodo29", Colors.violet),
    SimulatedAgentDefinition("vfrodo30", Colors.brown),
]


def get_simulated_agent_definition_by_id(frodo_id: str) -> SimulatedAgentDefinition | None:
    for agent in SIMULATED_AGENTS:
        if agent.id == frodo_id:
            return agent
    return None
