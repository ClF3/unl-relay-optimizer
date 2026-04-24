"""VDOT performance formulas.

All times are minutes, all distances are meters, and speeds are meters/minute.
"""

from __future__ import annotations

import math

OXYGEN_INTERCEPT = -4.60
OXYGEN_LINEAR = 0.182258
OXYGEN_QUADRATIC = 0.000104

FATIGUE_BASE = 0.8
FATIGUE_A = 0.1894393
FATIGUE_A_RATE = 0.012778
FATIGUE_B = 0.2989558
FATIGUE_B_RATE = 0.1932605


def _require_nonnegative_minutes(time_min: float) -> None:
    if time_min < 0:
        raise ValueError("time_min must be nonnegative")


def _require_positive_vdot(vdot: float) -> None:
    if vdot <= 0:
        raise ValueError("VDOT must be positive")


def fatigue_fraction(time_min: float) -> float:
    """Return the Daniels/Gilbert VO2max fraction for a race duration."""

    _require_nonnegative_minutes(time_min)
    return (
        FATIGUE_BASE
        + FATIGUE_A * math.exp(-FATIGUE_A_RATE * time_min)
        + FATIGUE_B * math.exp(-FATIGUE_B_RATE * time_min)
    )


def fatigue_fraction_derivative(time_min: float) -> float:
    """Return d/dt of the Daniels/Gilbert VO2max fraction."""

    _require_nonnegative_minutes(time_min)
    return (
        -FATIGUE_A * FATIGUE_A_RATE * math.exp(-FATIGUE_A_RATE * time_min)
        - FATIGUE_B * FATIGUE_B_RATE * math.exp(-FATIGUE_B_RATE * time_min)
    )


def oxygen_cost_from_speed(speed_m_per_min: float) -> float:
    """Return oxygen demand from speed using the Daniels running equation."""

    if speed_m_per_min < 0:
        raise ValueError("speed_m_per_min must be nonnegative")
    return (
        OXYGEN_INTERCEPT
        + OXYGEN_LINEAR * speed_m_per_min
        + OXYGEN_QUADRATIC * speed_m_per_min * speed_m_per_min
    )


def velocity_m_per_min(vdot: float, time_min: float) -> float:
    """Return average speed predicted for a VDOT and duration."""

    _require_positive_vdot(vdot)
    _require_nonnegative_minutes(time_min)
    required_oxygen = vdot * fatigue_fraction(time_min)
    discriminant = (
        OXYGEN_LINEAR * OXYGEN_LINEAR
        + 4 * OXYGEN_QUADRATIC * (required_oxygen - OXYGEN_INTERCEPT)
    )
    return (-OXYGEN_LINEAR + math.sqrt(discriminant)) / (2 * OXYGEN_QUADRATIC)


def velocity_derivative_m_per_min2(vdot: float, time_min: float) -> float:
    """Return d/dt of predicted average speed."""

    speed = velocity_m_per_min(vdot, time_min)
    denominator = OXYGEN_LINEAR + 2 * OXYGEN_QUADRATIC * speed
    return vdot * fatigue_fraction_derivative(time_min) / denominator


def distance_m(vdot: float, time_min: float) -> float:
    """Return distance covered by one runner over a continuous duration."""

    _require_nonnegative_minutes(time_min)
    if time_min == 0:
        return 0.0
    return time_min * velocity_m_per_min(vdot, time_min)


def time_for_distance_min(
    vdot: float,
    target_distance_m: float,
    *,
    tolerance: float = 1e-9,
    max_iterations: int = 120,
) -> float:
    """Return the duration required to cover a target distance."""

    _require_positive_vdot(vdot)
    if target_distance_m < 0:
        raise ValueError("target_distance_m must be nonnegative")
    if target_distance_m == 0:
        return 0.0

    high = max(1.0, target_distance_m / velocity_m_per_min(vdot, 0.0))
    while distance_m(vdot, high) < target_distance_m:
        high *= 2
        if high > 10_000_000:
            raise ValueError("could not bracket target distance")

    low = 0.0
    for _ in range(max_iterations):
        mid = (low + high) / 2
        if distance_m(vdot, mid) < target_distance_m:
            low = mid
        else:
            high = mid
        if high - low <= tolerance:
            break
    return (low + high) / 2


def marginal_distance_m_per_min(vdot: float, time_min: float) -> float:
    """Return d/dt of distance, the current marginal distance rate."""

    _require_nonnegative_minutes(time_min)
    return velocity_m_per_min(vdot, time_min) + (
        time_min * velocity_derivative_m_per_min2(vdot, time_min)
    )


def vdot_from_performance(distance: float, time_min: float) -> float:
    """Infer VDOT from a known distance and finish time."""

    if distance <= 0:
        raise ValueError("distance must be positive")
    if time_min <= 0:
        raise ValueError("time_min must be positive")
    speed = distance / time_min
    return oxygen_cost_from_speed(speed) / fatigue_fraction(time_min)
