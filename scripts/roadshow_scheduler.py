#!/usr/bin/env python3
"""Enumerate buffered same-day roadshow schedules from supplied travel times.

This helper does not query map APIs. Provide meeting constraints and leg times
in JSON; the script returns the best feasible timeline it can find.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple


def parse_time(value: Optional[str]) -> Optional[int]:
    if value in (None, ""):
        return None
    parts = str(value).strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time: {value!r}; expected HH:MM")
    return int(parts[0]) * 60 + int(parts[1])


def fmt_time(minutes: Optional[int]) -> str:
    if minutes is None:
        return ""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


@dataclass(frozen=True)
class Meeting:
    id: str
    name: str
    location: str
    duration: int
    fixed_start: Optional[int]
    window_start: Optional[int]
    window_end: Optional[int]
    priority: int
    contact: str = ""

    @property
    def is_fixed(self) -> bool:
        return self.fixed_start is not None


def normalize_minutes(value: Any, preference: str) -> Tuple[int, str, int]:
    """Return (minutes, mode, walking_penalty) from a leg value."""
    if isinstance(value, (int, float)):
        return int(value), "estimate", 0
    if not isinstance(value, dict):
        raise ValueError(f"Leg value must be number or object, got {value!r}")

    candidates: List[Tuple[str, int, int]] = []
    for mode, minutes in value.items():
        if mode in ("walk_minutes", "walking_minutes"):
            continue
        if isinstance(minutes, (int, float)):
            walk = int(value.get(f"{mode}_walk_minutes", value.get("walk_minutes", 0)) or 0)
            candidates.append((mode, int(minutes), walk))
    if not candidates:
        raise ValueError(f"Leg object has no numeric mode: {value!r}")

    pref = preference.lower()
    if pref in ("taxi", "taxi-first", "打车", "全程打车"):
        for mode, minutes, walk in candidates:
            if mode in ("taxi", "car", "ridehail", "打车"):
                return minutes, mode, walk
    if pref in ("subway", "metro", "地铁", "地铁优先"):
        for mode, minutes, walk in candidates:
            if mode in ("subway", "metro", "地铁"):
                return minutes, mode, walk
    if pref in ("energy", "energy-first", "体力优先"):
        fastest = min(candidates, key=lambda x: x[1])
        taxi = next((c for c in candidates if c[0] in ("taxi", "car", "ridehail", "打车")), None)
        if taxi and taxi[1] <= fastest[1] + 15:
            return taxi[1], taxi[0], taxi[2]
        return fastest[1], fastest[0], fastest[2]

    mode, minutes, walk = min(candidates, key=lambda x: x[1])
    return minutes, mode, walk


def get_leg(legs: Dict[str, Any], start: str, end: str, preference: str) -> Tuple[int, str, int]:
    if start == end:
        return 0, "same_place", 0
    key = f"{start}|{end}"
    rev_key = f"{end}|{start}"
    if key in legs:
        return normalize_minutes(legs[key], preference)
    if rev_key in legs:
        return normalize_minutes(legs[rev_key], preference)
    return 45, "missing_estimate", 0


def load_meetings(data: Dict[str, Any]) -> List[Meeting]:
    meetings = []
    for item in data.get("meetings", []):
        meetings.append(
            Meeting(
                id=str(item["id"]),
                name=str(item.get("name", item["id"])),
                location=str(item.get("location", item.get("address", item["id"]))),
                duration=int(item.get("duration", item.get("duration_minutes", 45))),
                fixed_start=parse_time(item.get("fixed_start")),
                window_start=parse_time(item.get("window_start")),
                window_end=parse_time(item.get("window_end")),
                priority=int(item.get("priority", 1)),
                contact=str(item.get("contact", "")),
            )
        )
    if not meetings:
        raise ValueError("Input JSON must include a non-empty meetings array")
    return meetings


def simulate(
    order: Iterable[Meeting],
    data: Dict[str, Any],
    args: argparse.Namespace,
) -> Tuple[float, List[Dict[str, Any]], List[str]]:
    legs = data.get("legs", {})
    preference = args.preference
    current_location = str(data.get("start_location", "START"))
    current_time = parse_time(data.get("start_time")) or 8 * 60
    timeline: List[Dict[str, Any]] = []
    warnings: List[str] = []
    total_travel = 0
    total_walk_penalty = 0
    total_wait = 0
    late_penalty = 0
    fixed_miss_penalty = 0

    for meeting in order:
        travel, mode, walk_penalty = get_leg(legs, current_location, meeting.location, preference)
        total_travel += travel
        total_walk_penalty += walk_penalty
        depart = current_time
        arrive = depart + travel

        required_pre = args.pre_fixed_buffer if meeting.is_fixed else args.pre_buffer
        earliest_start = meeting.fixed_start if meeting.is_fixed else meeting.window_start
        latest_end = (
            meeting.fixed_start + meeting.duration
            if meeting.is_fixed
            else meeting.window_end
        )

        if meeting.is_fixed:
            start = meeting.fixed_start or arrive
            if arrive > start - required_pre:
                fixed_miss_penalty += (arrive - (start - required_pre)) * (100 + meeting.priority * 20)
                warnings.append(
                    f"{meeting.name}: arrives {fmt_time(arrive)}, less than {required_pre} min before fixed {fmt_time(start)}"
                )
            wait = max(0, start - arrive)
        else:
            start = max(arrive + required_pre, earliest_start or -math.inf)
            if latest_end is not None and start + meeting.duration > latest_end:
                late_penalty += (start + meeting.duration - latest_end) * (50 + meeting.priority * 10)
                warnings.append(
                    f"{meeting.name}: ends {fmt_time(start + meeting.duration)}, after window end {fmt_time(latest_end)}"
                )
            wait = max(0, start - arrive)

        total_wait += wait
        end = start + meeting.duration
        timeline.append(
            {
                "depart": fmt_time(depart),
                "from": current_location,
                "travel_minutes": travel,
                "mode": mode,
                "arrive": fmt_time(arrive),
                "start": fmt_time(start),
                "end": fmt_time(end),
                "meeting_id": meeting.id,
                "name": meeting.name,
                "contact": meeting.contact,
                "location": meeting.location,
                "duration": meeting.duration,
                "fixed": meeting.is_fixed,
                "wait_or_buffer_minutes": wait,
            }
        )
        current_location = meeting.location
        current_time = end + args.post_buffer

    end_location = data.get("end_location")
    if end_location:
        travel, mode, walk_penalty = get_leg(legs, current_location, str(end_location), preference)
        total_travel += travel
        total_walk_penalty += walk_penalty
        timeline.append(
            {
                "depart": fmt_time(current_time),
                "from": current_location,
                "travel_minutes": travel,
                "mode": mode,
                "arrive": fmt_time(current_time + travel),
                "event": "end_transfer",
                "location": str(end_location),
            }
        )
        current_time += travel

    score = total_travel + total_wait * 0.2 + total_walk_penalty * 0.8 + late_penalty + fixed_miss_penalty
    score += max(0, len([w for w in warnings if "after window" in w])) * 200
    return score, timeline, warnings


def candidate_orders(meetings: List[Meeting], max_permutations: int) -> Iterable[Tuple[Meeting, ...]]:
    fixed = [m for m in meetings if m.is_fixed]
    if fixed:
        fixed_sorted = sorted(fixed, key=lambda m: m.fixed_start or 0)
        # Enumerating all meetings is simplest and catches cases where flexible
        # meetings fit before, between, or after fixed anchors.
    if math.factorial(len(meetings)) > max_permutations:
        flex_sorted = sorted(meetings, key=lambda m: (m.fixed_start is None, m.fixed_start or m.window_start or 24 * 60, -m.priority))
        yield tuple(flex_sorted)
        return
    yield from itertools.permutations(meetings)


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan a same-day roadshow schedule from supplied constraints.")
    parser.add_argument("input_json", help="Path to input JSON")
    parser.add_argument("--pre-buffer", type=int, default=10, help="Minutes before flexible meetings")
    parser.add_argument("--post-buffer", type=int, default=5, help="Minutes after each meeting")
    parser.add_argument("--pre-fixed-buffer", type=int, default=15, help="Minutes to arrive before fixed meetings")
    parser.add_argument("--preference", default="hybrid", help="efficiency, energy, taxi, subway, or hybrid")
    parser.add_argument("--max-permutations", type=int, default=40320, help="Safety cap; 40320 covers 8 meetings")
    args = parser.parse_args()

    with open(args.input_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    meetings = load_meetings(data)

    best: Optional[Tuple[float, List[Dict[str, Any]], List[str], Tuple[str, ...]]] = None
    checked = 0
    for order in candidate_orders(meetings, args.max_permutations):
        checked += 1
        score, timeline, warnings = simulate(order, data, args)
        order_ids = tuple(m.id for m in order)
        if best is None or score < best[0]:
            best = (score, timeline, warnings, order_ids)

    assert best is not None
    result = {
        "checked_orders": checked,
        "best_order": list(best[3]),
        "score": round(best[0], 2),
        "warnings": best[2],
        "timeline": best[1],
    }
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
