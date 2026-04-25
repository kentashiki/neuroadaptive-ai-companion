from __future__ import annotations

from models.state import UserState


STATE_PRESETS = {
    "focused": {"attention": 0.84},
    "distracted": {"attention": 0.32},
}


class DummyEEGReceiver:
    def __init__(self, initial_state: str = "distracted") -> None:
        self._current_state = self._make_state(initial_state)

    def _make_state(self, label: str) -> UserState:
        if label not in STATE_PRESETS:
            valid = ", ".join(sorted(STATE_PRESETS))
            raise ValueError(f"Unsupported state '{label}'. Valid states: {valid}.")
        preset = STATE_PRESETS[label]
        return UserState.create(
            attention=preset["attention"],
            label=label,
        )

    def get_state(self) -> UserState:
        return self._current_state

    def set_state(self, label: str) -> UserState:
        self._current_state = self._make_state(label)
        return self._current_state
