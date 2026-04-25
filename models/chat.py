from __future__ import annotations

from dataclasses import dataclass
import time


@dataclass(slots=True)
class ChatMessage:
    role: str
    content: str
    timestamp: float
    state_label: str | None = None
    avatar_path: str | None = None

    @classmethod
    def create(
        cls,
        *,
        role: str,
        content: str,
        state_label: str | None = None,
        avatar_path: str | None = None,
    ) -> "ChatMessage":
        return cls(
            role=role,
            content=content,
            timestamp=time.time(),
            state_label=state_label,
            avatar_path=avatar_path,
        )
