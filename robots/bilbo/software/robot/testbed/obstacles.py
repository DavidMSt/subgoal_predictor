from abc import ABC, abstractmethod
import dataclasses


@dataclasses.dataclass
class Obstacle(ABC):
    id: str
    x: float = 0.0
    y: float = 0.0

    @abstractmethod
    def set_state(self, x: float, y: float, psi: float | None) -> None:
        ...


@dataclasses.dataclass(kw_only=True)
class CircleObstacle(Obstacle):
    radius: float

    def set_state(self, x: float, y: float, psi: float | None) -> None:
        self.x = x
        self.y = y


@dataclasses.dataclass(kw_only=True)
class BoxObstacle(Obstacle):
    width: float
    height: float
    psi: float = 0.0

    def set_state(self, x: float, y: float, psi: float | None) -> None:
        self.x = x
        self.y = y
        if psi is not None:
            self.psi = psi
