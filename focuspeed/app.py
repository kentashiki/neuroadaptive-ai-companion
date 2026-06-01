from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import random
import time

from flask import Flask, jsonify, render_template


@dataclass(frozen=True)
class EEGSnapshot:
    attention: float
    playback_rate: float
    lsl_connected: bool
    raw_eeg: list[float]
    alpha_power: float
    beta_power: float
    theta_power: float
    low_beta_power: float
    high_beta_power: float
    alpha_beta_ratio: float
    theta_beta_ratio: float
    theta_alpha_ratio: float
    theta_alpha_over_beta: float


class DemoEEGStream:
    """Deterministic realtime-like EEG feature source for the demo UI."""

    def __init__(self) -> None:
        self.started_at = time.monotonic()
        self.random = random.Random(42)

    def snapshot(self) -> EEGSnapshot:
        elapsed = time.monotonic() - self.started_at
        slow_wave = math.sin(elapsed * 0.45)
        fast_wave = math.sin(elapsed * 1.35 + 0.8)
        attention = self._clamp01(0.58 + 0.26 * slow_wave + 0.1 * fast_wave)

        theta_power = 0.52 - 0.22 * attention + self._noise(0.015)
        alpha_power = 0.44 - 0.08 * attention + 0.04 * math.sin(elapsed * 0.8)
        beta_power = 0.30 + 0.34 * attention + self._noise(0.018)
        low_beta_power = beta_power * (0.55 + 0.05 * math.sin(elapsed * 0.7))
        high_beta_power = beta_power - low_beta_power
        lsl_connected = False

        return EEGSnapshot(
            attention=round(attention, 3),
            playback_rate=round(self._rate_for_attention(attention), 2),
            lsl_connected=lsl_connected,
            raw_eeg=self._raw_eeg(elapsed) if lsl_connected else [],
            alpha_power=round(alpha_power, 3),
            beta_power=round(beta_power, 3),
            theta_power=round(theta_power, 3),
            low_beta_power=round(low_beta_power, 3),
            high_beta_power=round(high_beta_power, 3),
            alpha_beta_ratio=round(alpha_power / beta_power, 3),
            theta_beta_ratio=round(theta_power / beta_power, 3),
            theta_alpha_ratio=round(theta_power / alpha_power, 3),
            theta_alpha_over_beta=round((theta_power + alpha_power) / beta_power, 3),
        )

    def _noise(self, width: float) -> float:
        return self.random.uniform(-width, width)

    def _raw_eeg(self, elapsed: float, points: int = 180) -> list[float]:
        return [
            round(
                32 * math.sin((elapsed + index * 0.01) * 18)
                + 12 * math.sin((elapsed + index * 0.01) * 43),
                2,
            )
            for index in range(points)
        ]

    @staticmethod
    def _clamp01(value: float) -> float:
        return max(0.0, min(1.0, value))

    @staticmethod
    def _rate_for_attention(attention: float) -> float:
        # Low concentration slows speech down, high concentration allows faster listening.
        return max(0.75, min(1.5, 0.75 + attention * 0.75))


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    eeg_stream = DemoEEGStream()

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.get("/api/eeg")
    def api_eeg():
        return jsonify(asdict(eeg_stream.snapshot()))

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True, port=5050, use_reloader=False)
