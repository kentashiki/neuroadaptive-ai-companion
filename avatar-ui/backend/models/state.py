from __future__ import annotations

from dataclasses import dataclass
import time


@dataclass
class UserState:
    attention: float
    label: str
    timestamp: float

    @classmethod
    def create(cls, attention: float, label: str) -> "UserState":
        return cls(
            attention=max(0.0, min(1.0, attention)),
            label=label,
            timestamp=time.time(),
        )
