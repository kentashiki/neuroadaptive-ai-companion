from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TutorAction:
    message: str
    next_level: int
    action: str
