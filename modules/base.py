from abc import ABC, abstractmethod
from models import ProspectRecord


class BaseModule(ABC):
    def __init__(self, config: dict, states: list[str]):
        self.config = config
        self.states = states
        self.verticals = config.get("verticals", {})
        self.icp = config.get("icp", {})

    @property
    @abstractmethod
    def channel_name(self) -> str:
        pass

    @abstractmethod
    def run(self, active_verticals: list[str] | None = None) -> list[ProspectRecord]:
        pass

    def get_active_verticals(self, requested: list[str] | None) -> dict:
        if requested:
            return {k: v for k, v in self.verticals.items() if k in requested}
        return self.verticals

    def log(self, msg: str):
        print(f"[{self.channel_name.upper()}] {msg}")
