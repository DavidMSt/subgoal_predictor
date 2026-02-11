import dataclasses

from core.utils.files import get_absolute_path
from core.utils.states import State
from core.utils.uuid_utils import generate_uuid

# ======================================================================================================================
EXPERIMENT_DIR = get_absolute_path('./experiments/')


# === COMMON OBJECTS AND CONFIGS =======================================================================================
@dataclasses.dataclass
class BoxObstacle_Config:
    id: str | None = None
    width: float = 0
    height: float = 0

    # Convenience fields for YAML shorthand (e.g. size: [1, 0.5], state: [1, 1, 1.57])
    size: list | None = dataclasses.field(default=None, repr=False)
    state: list | None = dataclasses.field(default=None, repr=False)
    type: str | None = dataclasses.field(default=None, repr=False)

    def __post_init__(self):
        self.id = self.id or generate_uuid(prefix="box_obstacle_")
        if self.size is not None and len(self.size) >= 2:
            if self.width == 0:
                self.width = float(self.size[0])
            if self.height == 0:
                self.height = float(self.size[1])
            self.size = None
        self.type = None  # Not needed after init
        # state is consumed by VirtualTestbed.init(), not cleaned here


@dataclasses.dataclass
class BoxObstacle_State:
    x: float = 0
    y: float = 0
    psi: float = 0


@dataclasses.dataclass
class BILBO_DynamicState(State):
    x: float = 0.0
    y: float = 0.0
    v: float = 0.0
    theta: float = 0.0
    theta_dot: float = 0.0
    psi: float = 0.0
    psi_dot: float = 0.0
