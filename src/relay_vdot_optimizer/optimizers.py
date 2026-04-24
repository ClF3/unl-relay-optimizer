"""Optimization routines for relay VDOT allocation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .vdot import (
    distance_m,
    marginal_distance_m_per_min,
    time_for_distance_min,
    velocity_m_per_min,
)


@dataclass(frozen=True)
class Allocation:
    """Time and distance assigned to one runner."""

    runner: int
    vdot: float
    time_min: float
    distance_m: float
    average_speed_m_per_min: float
    marginal_speed_m_per_min: float

    @property
    def pace_min_per_km(self) -> float | None:
        if self.average_speed_m_per_min <= 0:
            return None
        return 1000.0 / self.average_speed_m_per_min


@dataclass(frozen=True)
class OptimizationResult:
    """An optimization result."""

    mode: str
    total_time_min: float
    total_distance_m: float
    allocations: tuple[Allocation, ...]
    details: dict[str, float | int | bool | str]


def _validate_inputs(vdots: Iterable[float], total_time_min: float) -> tuple[float, ...]:
    vdot_values = tuple(float(vdot) for vdot in vdots)
    if not vdot_values:
        raise ValueError("at least one VDOT value is required")
    if total_time_min <= 0:
        raise ValueError("total_time_min must be positive")
    for vdot in vdot_values:
        if vdot <= 0:
            raise ValueError("VDOT values must be positive")
    return vdot_values


def _build_allocations(vdots: tuple[float, ...], times: list[float]) -> tuple[Allocation, ...]:
    allocations: list[Allocation] = []
    for index, (vdot, time_min) in enumerate(zip(vdots, times), start=1):
        distance = distance_m(vdot, time_min)
        avg_speed = distance / time_min if time_min > 0 else 0.0
        marginal = marginal_distance_m_per_min(vdot, time_min)
        allocations.append(
            Allocation(
                runner=index,
                vdot=vdot,
                time_min=time_min,
                distance_m=distance,
                average_speed_m_per_min=avg_speed,
                marginal_speed_m_per_min=marginal,
            )
        )
    return tuple(allocations)


def _build_allocations_from_distances(
    vdots: tuple[float, ...],
    times: list[float],
    distances: list[float],
) -> tuple[Allocation, ...]:
    allocations: list[Allocation] = []
    for index, (vdot, time_min, distance) in enumerate(zip(vdots, times, distances), start=1):
        avg_speed = distance / time_min if time_min > 0 else 0.0
        marginal = marginal_distance_m_per_min(vdot, time_min)
        allocations.append(
            Allocation(
                runner=index,
                vdot=vdot,
                time_min=time_min,
                distance_m=distance,
                average_speed_m_per_min=avg_speed,
                marginal_speed_m_per_min=marginal,
            )
        )
    return tuple(allocations)


def _time_at_marginal(
    vdot: float,
    target_marginal: float,
    max_time_min: float,
    iterations: int,
) -> float:
    start_marginal = marginal_distance_m_per_min(vdot, 0.0)
    if start_marginal <= target_marginal:
        return 0.0

    end_marginal = marginal_distance_m_per_min(vdot, max_time_min)
    if end_marginal >= target_marginal:
        return max_time_min

    low = 0.0
    high = max_time_min
    for _ in range(iterations):
        mid = (low + high) / 2
        if marginal_distance_m_per_min(vdot, mid) > target_marginal:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def _marginals_look_nonincreasing(
    vdots: tuple[float, ...],
    total_time_min: float,
    samples: int = 400,
    tolerance: float = 1e-7,
) -> bool:
    if samples <= 1:
        return True
    for vdot in vdots:
        previous = marginal_distance_m_per_min(vdot, 0.0)
        for step in range(1, samples + 1):
            time_min = total_time_min * step / samples
            current = marginal_distance_m_per_min(vdot, time_min)
            if current > previous + tolerance:
                return False
            previous = current
    return True


def optimize_concave(
    vdots: Iterable[float],
    total_time_min: float,
    *,
    iterations: int = 100,
    monotonicity_samples: int = 400,
) -> OptimizationResult:
    """Optimize by equalizing marginal distance under the concavity assumption.

    This is exact for the concave relaxation: every active runner receives a
    duration whose marginal distance equals a common lambda.
    """

    vdot_values = _validate_inputs(vdots, total_time_min)
    high = max(marginal_distance_m_per_min(vdot, 0.0) for vdot in vdot_values)
    low = 0.0

    for _ in range(iterations):
        mid = (low + high) / 2
        times = [
            _time_at_marginal(vdot, mid, total_time_min, iterations)
            for vdot in vdot_values
        ]
        if sum(times) > total_time_min:
            low = mid
        else:
            high = mid

    lambda_value = (low + high) / 2
    times = [
        _time_at_marginal(vdot, lambda_value, total_time_min, iterations)
        for vdot in vdot_values
    ]

    total_assigned = sum(times)
    if total_assigned > 0:
        scale = total_time_min / total_assigned
        times = [time_min * scale for time_min in times]

    allocations = _build_allocations(vdot_values, times)
    total_distance = sum(allocation.distance_m for allocation in allocations)
    monotone = _marginals_look_nonincreasing(
        vdot_values,
        total_time_min,
        samples=monotonicity_samples,
    )
    return OptimizationResult(
        mode="concave",
        total_time_min=total_time_min,
        total_distance_m=total_distance,
        allocations=allocations,
        details={
            "lambda_m_per_min": lambda_value,
            "iterations": iterations,
            "marginals_sampled_nonincreasing": monotone,
            "monotonicity_samples": monotonicity_samples,
        },
    )


def optimize_search(
    vdots: Iterable[float],
    total_time_min: float,
    *,
    unit_sec: float,
) -> OptimizationResult:
    """Search the globally optimal discrete allocation with dynamic programming."""

    vdot_values = _validate_inputs(vdots, total_time_min)
    if unit_sec <= 0:
        raise ValueError("unit_sec must be positive")

    total_sec = total_time_min * 60.0
    units_float = total_sec / unit_sec
    units = round(units_float)
    if abs(units_float - units) > 1e-8:
        raise ValueError("total time must be an integer multiple of unit_sec")

    unit_min = unit_sec / 60.0
    values_by_runner = [
        [distance_m(vdot, units_for_runner * unit_min) for units_for_runner in range(units + 1)]
        for vdot in vdot_values
    ]

    minus_inf = float("-inf")
    previous = [minus_inf] * (units + 1)
    previous[0] = 0.0
    choices: list[list[int]] = []

    for runner_values in values_by_runner:
        current = [minus_inf] * (units + 1)
        choice_for_total = [0] * (units + 1)
        for total_units in range(units + 1):
            best_distance = minus_inf
            best_take = 0
            for take_units in range(total_units + 1):
                candidate = previous[total_units - take_units] + runner_values[take_units]
                if candidate > best_distance:
                    best_distance = candidate
                    best_take = take_units
            current[total_units] = best_distance
            choice_for_total[total_units] = best_take
        previous = current
        choices.append(choice_for_total)

    time_units = [0] * len(vdot_values)
    remaining_units = units
    for runner_index in range(len(vdot_values) - 1, -1, -1):
        take = choices[runner_index][remaining_units]
        time_units[runner_index] = take
        remaining_units -= take

    times = [time_unit * unit_min for time_unit in time_units]
    allocations = _build_allocations(vdot_values, times)
    total_distance = sum(allocation.distance_m for allocation in allocations)
    return OptimizationResult(
        mode="search",
        total_time_min=total_time_min,
        total_distance_m=total_distance,
        allocations=allocations,
        details={
            "unit_sec": unit_sec,
            "time_units": units,
            "states_evaluated": len(vdot_values) * (units + 1) * (units + 2) // 2,
        },
    )


def optimize_distance_search(
    vdots: Iterable[float],
    total_time_min: float,
    *,
    unit_m: float = 400.0,
    feasibility_tolerance_min: float = 1e-7,
) -> OptimizationResult:
    """Search the best allocation when handoffs happen on distance units.

    The DP minimizes total time for each completed distance-unit count, then
    selects the largest count whose time fits inside the relay time limit.
    """

    vdot_values = _validate_inputs(vdots, total_time_min)
    if unit_m <= 0:
        raise ValueError("unit_m must be positive")

    first_unit_times = [time_for_distance_min(vdot, unit_m) for vdot in vdot_values]
    fastest_unit_time = min(first_unit_times)
    max_units = int(total_time_min / fastest_unit_time) + 1
    if max_units < 1:
        max_units = 1

    times_by_runner = [
        [
            time_for_distance_min(vdot, distance_units * unit_m)
            for distance_units in range(max_units + 1)
        ]
        for vdot in vdot_values
    ]

    infinity = float("inf")
    previous = [infinity] * (max_units + 1)
    previous[0] = 0.0
    choices: list[list[int]] = []

    for runner_times in times_by_runner:
        current = [infinity] * (max_units + 1)
        choice_for_total = [0] * (max_units + 1)
        for total_units in range(max_units + 1):
            best_time = infinity
            best_take = 0
            for take_units in range(total_units + 1):
                candidate = previous[total_units - take_units] + runner_times[take_units]
                if candidate < best_time:
                    best_time = candidate
                    best_take = take_units
            current[total_units] = best_time
            choice_for_total[total_units] = best_take
        previous = current
        choices.append(choice_for_total)

    best_units = 0
    for distance_units, time_min in enumerate(previous):
        if time_min <= total_time_min + feasibility_tolerance_min:
            best_units = distance_units

    distance_units_by_runner = [0] * len(vdot_values)
    remaining_units = best_units
    for runner_index in range(len(vdot_values) - 1, -1, -1):
        take = choices[runner_index][remaining_units]
        distance_units_by_runner[runner_index] = take
        remaining_units -= take

    times = [
        times_by_runner[runner_index][distance_units]
        for runner_index, distance_units in enumerate(distance_units_by_runner)
    ]
    distances = [distance_units * unit_m for distance_units in distance_units_by_runner]
    allocations = _build_allocations_from_distances(vdot_values, times, distances)
    total_used_time = sum(times)
    total_distance = best_units * unit_m

    return OptimizationResult(
        mode="distance-search",
        total_time_min=total_time_min,
        total_distance_m=total_distance,
        allocations=allocations,
        details={
            "unit_m": unit_m,
            "distance_units": best_units,
            "searched_distance_units": max_units,
            "used_time_min": total_used_time,
            "unused_time_min": max(0.0, total_time_min - total_used_time),
            "states_evaluated": len(vdot_values) * (max_units + 1) * (max_units + 2) // 2,
        },
    )
