from __future__ import annotations

from dataclasses import dataclass
import time


@dataclass
class ChatMessage:
    role: str
    content: str
    timestamp: float
    state_label: str | None = None

    @classmethod
    def create(cls, *, role: str, content: str, state_label: str | None = None) -> "ChatMessage":
        return cls(
            role=role,
            content=content,
            timestamp=time.time(),
            state_label=state_label,
        )
