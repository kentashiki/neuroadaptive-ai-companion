from __future__ import annotations


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def estimate_state(beta_theta_ratio: float, beta_alpha_ratio: float) -> dict[str, float | str]:
    attention = clamp01((beta_theta_ratio - 0.5) / 1.5)
    arousal = clamp01((beta_alpha_ratio - 0.5) / 1.5)

    if attention >= 0.7 and arousal >= 0.6:
        label = "focused"
    elif attention < 0.4 and arousal < 0.5:
        label = "low_arousal"
    elif attention < 0.5:
        label = "distracted"
    else:
        label = "neutral"

    return {"attention": attention, "arousal": arousal, "label": label}
