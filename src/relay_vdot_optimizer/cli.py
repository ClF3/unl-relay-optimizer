"""Command line interface for relay VDOT optimization."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from .optimizers import (
    Allocation,
    OptimizationResult,
    optimize_concave,
    optimize_distance_search,
    optimize_search,
)


def _parse_vdots(raw_values: list[str]) -> list[float]:
    values: list[float] = []
    for raw in raw_values:
        for item in raw.split(","):
            stripped = item.strip()
            if stripped:
                values.append(float(stripped))
    if not values:
        raise argparse.ArgumentTypeError("at least one VDOT value is required")
    return values


def _format_duration(time_min: float) -> str:
    total_seconds = int(round(time_min * 60))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:d}:{seconds:02d}"


def _format_pace(pace_min_per_km: float | None) -> str:
    if pace_min_per_km is None:
        return "-"
    minutes = int(pace_min_per_km)
    seconds = int(round((pace_min_per_km - minutes) * 60))
    if seconds == 60:
        minutes += 1
        seconds = 0
    return f"{minutes:d}:{seconds:02d}/km"


def _allocation_to_json(allocation: Allocation) -> dict[str, float | int | None]:
    data = asdict(allocation)
    data["pace_min_per_km"] = allocation.pace_min_per_km
    return data


def _result_to_json(result: OptimizationResult) -> str:
    data = {
        "mode": result.mode,
        "total_time_min": result.total_time_min,
        "total_distance_m": result.total_distance_m,
        "total_distance_km": result.total_distance_m / 1000.0,
        "details": result.details,
        "allocations": [_allocation_to_json(allocation) for allocation in result.allocations],
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def _print_table(result: OptimizationResult, *, quiet_warning: bool) -> None:
    if (
        result.mode == "concave"
        and not quiet_warning
        and not result.details.get("marginals_sampled_nonincreasing", True)
    ):
        print(
            "Warning: sampled marginal distance is not globally nonincreasing over this time range; "
            "consider checking with a search mode.",
            file=sys.stderr,
        )

    print(f"Mode: {result.mode}")
    print(f"Total time: {_format_duration(result.total_time_min)}")
    print(f"Total distance: {result.total_distance_m / 1000.0:.3f} km")
    if result.mode == "concave":
        print(f"Lambda: {result.details['lambda_m_per_min']:.3f} m/min")
    if result.mode == "search":
        print(
            f"Unit: {result.details['unit_sec']:g} sec, "
            f"time units: {result.details['time_units']}"
        )
    if result.mode == "distance-search":
        print(
            f"Unit: {result.details['unit_m']:g} m, "
            f"distance units: {result.details['distance_units']}, "
            f"unused time: {_format_duration(float(result.details['unused_time_min']))}"
        )
    print()

    rows = [
        [
            "Runner",
            "VDOT",
            "Time",
            "Distance",
            "Avg speed",
            "Pace",
            "Marginal",
        ]
    ]
    for allocation in result.allocations:
        rows.append(
            [
                str(allocation.runner),
                f"{allocation.vdot:.2f}",
                _format_duration(allocation.time_min),
                f"{allocation.distance_m / 1000.0:.3f} km",
                f"{allocation.average_speed_m_per_min:.2f} m/min",
                _format_pace(allocation.pace_min_per_km),
                f"{allocation.marginal_speed_m_per_min:.2f} m/min",
            ]
        )

    widths = [max(len(row[column]) for row in rows) for column in range(len(rows[0]))]
    for index, row in enumerate(rows):
        line = "  ".join(value.ljust(widths[column]) for column, value in enumerate(row))
        print(line)
        if index == 0:
            print("  ".join("-" * width for width in widths))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="relay-vdot",
        description="Optimize relay time allocation from runner VDOT values.",
    )
    parser.add_argument(
        "--total-time",
        "-T",
        type=float,
        required=True,
        help="Total relay time in minutes.",
    )
    parser.add_argument(
        "--vdots",
        nargs="+",
        required=True,
        help="Runner VDOT values, separated by spaces or commas.",
    )
    parser.add_argument(
        "--runners",
        "-N",
        type=int,
        help="Optional runner count check. Must match the number of VDOT values.",
    )
    parser.add_argument(
        "--mode",
        choices=("concave", "search", "time-search", "distance-search"),
        default="concave",
        help="'search' and 'time-search' use time units; 'distance-search' uses distance units.",
    )
    parser.add_argument(
        "--unit-sec",
        type=float,
        help="Minimum time unit in seconds. Required for search/time-search mode.",
    )
    parser.add_argument(
        "--unit-m",
        type=float,
        default=400.0,
        help="Minimum distance unit in meters for distance-search mode. Defaults to 400.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON.",
    )
    parser.add_argument(
        "--quiet-warning",
        action="store_true",
        help="Hide concavity sampling warnings.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        vdots = _parse_vdots(args.vdots)
        if args.runners is not None and args.runners != len(vdots):
            parser.error(f"--runners is {args.runners}, but {len(vdots)} VDOT values were supplied")

        if args.mode in ("search", "time-search"):
            if args.unit_sec is None:
                parser.error("--unit-sec is required in search/time-search mode")
            result = optimize_search(vdots, args.total_time, unit_sec=args.unit_sec)
        elif args.mode == "distance-search":
            result = optimize_distance_search(vdots, args.total_time, unit_m=args.unit_m)
        else:
            result = optimize_concave(vdots, args.total_time)

        if args.json:
            print(_result_to_json(result))
        else:
            _print_table(result, quiet_warning=args.quiet_warning)
    except ValueError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
