#!/usr/bin/env python3
"""Optimize a same-day roadshow route using live Amap leg estimates.

The script asks Amap/Gaode for pairwise driving and transit legs, then
enumerates meeting orders and scores them against fixed slots, flexible
windows, buffers, walking burden, lunch/rest needs, and user preference.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple


DEFAULT_TIMEOUT = 15


def parse_time(value: Optional[str]) -> Optional[int]:
    if value in (None, ""):
        return None
    parts = str(value).strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time {value!r}; expected HH:MM")
    return int(parts[0]) * 60 + int(parts[1])


def fmt_time(minutes: Optional[int]) -> str:
    if minutes is None:
        return ""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def compact_address(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


@dataclass(frozen=True)
class Stop:
    id: str
    name: str
    location: str
    address: str = ""


@dataclass(frozen=True)
class Meeting(Stop):
    duration: int = 45
    fixed_start: Optional[int] = None
    window_start: Optional[int] = None
    window_end: Optional[int] = None
    priority: int = 1
    contact: str = ""
    cluster: str = ""

    @property
    def is_fixed(self) -> bool:
        return self.fixed_start is not None


@dataclass
class Leg:
    origin: str
    destination: str
    mode: str
    minutes: int
    distance_m: int = 0
    walking_m: int = 0
    provider: str = "amap"
    note: str = ""


def http_json(url: str) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "sell-side-roadshow-planner/2.1",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
        body = response.read().decode("utf-8", errors="replace")
    return json.loads(body)


def api_get(endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
    url = endpoint + "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
    return http_json(url)


def is_coord(value: str) -> bool:
    return bool(re.match(r"^\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*$", value or ""))


def geocode(address: str, city: str, key: str) -> Tuple[str, str]:
    data = api_get(
        "https://restapi.amap.com/v3/geocode/geo",
        {"key": key, "address": address, "city": city},
    )
    if data.get("status") != "1" or not data.get("geocodes"):
        raise RuntimeError(f"Amap geocode failed for {address!r}: {data.get('info') or data}")
    item = data["geocodes"][0]
    location = str(item.get("location", ""))
    formatted = str(item.get("formatted_address", address))
    if not is_coord(location):
        raise RuntimeError(f"Amap geocode returned invalid location for {address!r}: {location!r}")
    return location, formatted


def resolve_stop(raw: Dict[str, Any], city: str, key: str, default_id: str) -> Stop:
    stop_id = str(raw.get("id") or default_id)
    name = str(raw.get("name") or raw.get("institution") or stop_id)
    location = str(raw.get("location") or raw.get("coord") or "")
    address = str(raw.get("address") or "")
    if not location:
        query = address or name
        location, formatted = geocode(query, city, key)
        address = address or formatted
    elif not is_coord(location):
        location, formatted = geocode(location, city, key)
        address = address or formatted
    return Stop(id=stop_id, name=name, location=location.replace(" ", ""), address=address)


def resolve_meeting(raw: Dict[str, Any], city: str, key: str, idx: int) -> Meeting:
    stop = resolve_stop(raw, city, key, f"m{idx}")
    return Meeting(
        id=stop.id,
        name=stop.name,
        location=stop.location,
        address=stop.address,
        duration=int(raw.get("duration", raw.get("duration_minutes", 45))),
        fixed_start=parse_time(raw.get("fixed_start")),
        window_start=parse_time(raw.get("window_start")),
        window_end=parse_time(raw.get("window_end")),
        priority=int(raw.get("priority", 1)),
        contact=str(raw.get("contact", "")),
        cluster=str(raw.get("cluster", "")),
    )


def seconds_to_minutes(value: Any) -> int:
    try:
        return int(math.ceil(float(value) / 60.0))
    except (TypeError, ValueError):
        return 0


def parse_walking_m(segment: Dict[str, Any]) -> int:
    walking = segment.get("walking") or {}
    if not isinstance(walking, dict):
        return 0
    distance = walking.get("distance", 0)
    try:
        return int(float(distance or 0))
    except (TypeError, ValueError):
        return 0


def amap_driving(origin: Stop, destination: Stop, key: str, strategy: int = 10) -> Leg:
    data = api_get(
        "https://restapi.amap.com/v3/direction/driving",
        {
            "key": key,
            "origin": origin.location,
            "destination": destination.location,
            "strategy": strategy,
            "extensions": "base",
        },
    )
    if data.get("status") != "1":
        return Leg(origin.id, destination.id, "taxi", 45, provider="amap_error", note=str(data.get("info") or data))
    paths = (data.get("route") or {}).get("paths") or []
    if not paths:
        return Leg(origin.id, destination.id, "taxi", 45, provider="amap_missing", note="driving route missing")
    path = paths[0]
    return Leg(
        origin=origin.id,
        destination=destination.id,
        mode="taxi",
        minutes=seconds_to_minutes(path.get("duration")),
        distance_m=int(float(path.get("distance") or 0)),
    )


def amap_transit(origin: Stop, destination: Stop, city: str, key: str) -> Leg:
    data = api_get(
        "https://restapi.amap.com/v3/direction/transit/integrated",
        {
            "key": key,
            "origin": origin.location,
            "destination": destination.location,
            "city": city,
            "cityd": city,
            "strategy": 0,
        },
    )
    if data.get("status") != "1":
        return Leg(origin.id, destination.id, "transit", 60, provider="amap_error", note=str(data.get("info") or data))
    transits = (data.get("route") or {}).get("transits") or []
    if not transits:
        return Leg(origin.id, destination.id, "transit", 60, provider="amap_missing", note="transit route missing")
    item = transits[0]
    walking_m = 0
    for segment in item.get("segments") or []:
        if isinstance(segment, dict):
            walking_m += parse_walking_m(segment)
    if not walking_m:
        try:
            walking_m = int(float(item.get("walking_distance") or 0))
        except (TypeError, ValueError):
            walking_m = 0
    return Leg(
        origin=origin.id,
        destination=destination.id,
        mode="transit",
        minutes=seconds_to_minutes(item.get("duration")),
        distance_m=int(float(item.get("distance") or 0)),
        walking_m=walking_m,
    )


def build_matrix(stops: List[Stop], city: str, key: str, pause: float) -> Dict[str, Dict[str, Leg]]:
    matrix: Dict[str, Dict[str, Leg]] = {}
    for origin in stops:
        for destination in stops:
            if origin.id == destination.id:
                continue
            key_pair = f"{origin.id}|{destination.id}"
            driving = amap_driving(origin, destination, key)
            if pause:
                time.sleep(pause)
            transit = amap_transit(origin, destination, city, key)
            if pause:
                time.sleep(pause)
            matrix[key_pair] = {"taxi": driving, "transit": transit}
    return matrix


def preference_settings(data: Dict[str, Any], args: argparse.Namespace) -> Dict[str, float]:
    preference = (args.preference or data.get("preference") or "hybrid").lower()
    attire = " ".join(str(x).lower() for x in data.get("attire", []))
    high_walk_cost = any(token in preference + attire for token in ["energy", "体力", "high_heels", "heels", "formal", "正装", "高跟"])
    if preference in ("taxi", "taxi-first", "全程打车", "打车"):
        walk_weight = 0.035 if high_walk_cost else 0.015
        taxi_bias = -6.0
    elif preference in ("subway", "metro", "地铁", "地铁优先"):
        walk_weight = 0.01 if not high_walk_cost else 0.025
        taxi_bias = 4.0
    elif preference in ("efficiency", "efficiency-first", "效率优先"):
        walk_weight = 0.01 if not high_walk_cost else 0.02
        taxi_bias = 0.0
    else:
        walk_weight = 0.02 if high_walk_cost else 0.012
        taxi_bias = -3.0 if high_walk_cost else 0.0
    return {
        "walk_weight": walk_weight,
        "taxi_bias": taxi_bias,
        "preference": preference,
        "high_walk_cost": 1.0 if high_walk_cost else 0.0,
    }


def choose_leg(matrix: Dict[str, Dict[str, Leg]], start: str, end: str, settings: Dict[str, float]) -> Tuple[Leg, float]:
    if start == end:
        leg = Leg(start, end, "same_place", 0)
        return leg, 0.0
    options = matrix.get(f"{start}|{end}")
    if not options:
        leg = Leg(start, end, "missing_estimate", 45, provider="missing", note="no Amap matrix entry")
        return leg, 80.0

    scored: List[Tuple[float, Leg]] = []
    for leg in options.values():
        score = float(leg.minutes)
        score += float(leg.walking_m) * settings["walk_weight"]
        if leg.mode == "taxi":
            score += settings["taxi_bias"]
        if leg.provider != "amap":
            score += 20.0
        scored.append((score, leg))
    scored.sort(key=lambda item: item[0])
    return scored[0][1], scored[0][0]


def candidate_orders(meetings: List[Meeting], max_permutations: int) -> Iterable[Tuple[Meeting, ...]]:
    total = math.factorial(len(meetings))
    if total <= max_permutations:
        yield from itertools.permutations(meetings)
        return

    fixed_sorted = sorted(
        meetings,
        key=lambda m: (
            m.fixed_start is None,
            m.fixed_start if m.fixed_start is not None else (m.window_start or 24 * 60),
            -m.priority,
        ),
    )
    yield tuple(fixed_sorted)


def find_lunch_gap(events: List[Dict[str, Any]], lunch: Dict[str, Any]) -> Tuple[bool, List[str]]:
    if not lunch or not lunch.get("enabled", True):
        return True, []
    earliest = parse_time(lunch.get("earliest")) or 12 * 60
    latest = parse_time(lunch.get("latest")) or 13 * 60 + 30
    duration = int(lunch.get("duration", 40))
    notes: List[str] = []
    gaps: List[Tuple[int, int, str]] = []

    prev_end: Optional[int] = None
    prev_place = ""
    for event in events:
        start = parse_time(event.get("start"))
        end = parse_time(event.get("end"))
        if start is not None and prev_end is not None:
            gap_start = max(prev_end, earliest)
            gap_end = min(start, latest)
            if gap_end - gap_start >= duration:
                gaps.append((gap_start, gap_end, prev_place))
        if end is not None:
            prev_end = end
            prev_place = str(event.get("name") or event.get("meeting_id") or "")

    if gaps:
        best = max(gaps, key=lambda g: g[1] - g[0])
        notes.append(f"lunch gap {fmt_time(best[0])}-{fmt_time(best[0] + duration)} after {best[2] or 'previous stop'}")
        return True, notes
    notes.append(f"no {duration} min lunch gap inside {fmt_time(earliest)}-{fmt_time(latest)}")
    return False, notes


def simulate(
    order: Iterable[Meeting],
    data: Dict[str, Any],
    matrix: Dict[str, Dict[str, Leg]],
    args: argparse.Namespace,
) -> Tuple[float, List[Dict[str, Any]], List[str], Dict[str, Any]]:
    settings = preference_settings(data, args)
    current_location = str(data["start"]["id"])
    current_time = parse_time(data.get("start_time")) or 8 * 60
    timeline: List[Dict[str, Any]] = []
    warnings: List[str] = []
    stats = {
        "travel_minutes": 0,
        "taxi_segments": 0,
        "transit_segments": 0,
        "walking_m": 0,
        "wait_minutes": 0,
        "fixed_miss_minutes": 0,
        "window_overrun_minutes": 0,
    }
    score = 0.0

    for meeting in order:
        leg, leg_score = choose_leg(matrix, current_location, meeting.id, settings)
        depart = current_time
        arrive = depart + leg.minutes
        required_pre = args.pre_fixed_buffer if meeting.is_fixed else args.pre_buffer

        if meeting.is_fixed:
            start = meeting.fixed_start or arrive
            miss = max(0, arrive - (start - required_pre))
            if miss:
                stats["fixed_miss_minutes"] += miss
                score += miss * (120 + meeting.priority * 25)
                warnings.append(
                    f"{meeting.name}: {fmt_time(arrive)}到，距离固定{fmt_time(start)}不足{required_pre}分钟"
                )
        else:
            start = max(arrive + required_pre, meeting.window_start or -math.inf)
            if meeting.window_end is not None and start + meeting.duration > meeting.window_end:
                overrun = start + meeting.duration - meeting.window_end
                stats["window_overrun_minutes"] += overrun
                score += overrun * (60 + meeting.priority * 15)
                warnings.append(
                    f"{meeting.name}: {fmt_time(start + meeting.duration)}结束，超过窗口{fmt_time(meeting.window_end)}"
                )

        wait = max(0, start - arrive)
        end = start + meeting.duration
        stats["travel_minutes"] += leg.minutes
        stats["walking_m"] += leg.walking_m
        stats["wait_minutes"] += wait
        if leg.mode == "taxi":
            stats["taxi_segments"] += 1
        elif leg.mode == "transit":
            stats["transit_segments"] += 1

        score += leg_score + wait * 0.18
        timeline.append(
            {
                "depart": fmt_time(depart),
                "from": current_location,
                "travel_minutes": leg.minutes,
                "mode": leg.mode,
                "distance_km": round(leg.distance_m / 1000, 1) if leg.distance_m else None,
                "walking_m": leg.walking_m,
                "arrive": fmt_time(arrive),
                "start": fmt_time(start),
                "end": fmt_time(end),
                "meeting_id": meeting.id,
                "name": meeting.name,
                "contact": meeting.contact,
                "address": meeting.address,
                "cluster": meeting.cluster,
                "duration": meeting.duration,
                "fixed": meeting.is_fixed,
                "wait_or_buffer_minutes": wait,
            }
        )
        current_location = meeting.id
        current_time = end + args.post_buffer

    end = data.get("end")
    if isinstance(end, dict) and end.get("id"):
        end_stop = resolve_stop(end, str(data.get("city", "")), os.environ.get("AMAP_KEY") or os.environ.get("AMAP_API_KEY") or "", "END")
        leg, leg_score = choose_leg(matrix, current_location, end_stop.id, settings)
        score += leg_score
        stats["travel_minutes"] += leg.minutes
        stats["walking_m"] += leg.walking_m
        timeline.append(
            {
                "depart": fmt_time(current_time),
                "from": current_location,
                "travel_minutes": leg.minutes,
                "mode": leg.mode,
                "distance_km": round(leg.distance_m / 1000, 1) if leg.distance_m else None,
                "walking_m": leg.walking_m,
                "arrive": fmt_time(current_time + leg.minutes),
                "event": "end_transfer",
                "location": end_stop.name,
                "address": end_stop.address,
            }
        )

    lunch_ok, lunch_notes = find_lunch_gap(timeline, data.get("lunch") or {})
    stats["lunch_ok"] = lunch_ok
    if not lunch_ok:
        score += 180
        warnings.extend(lunch_notes)
    else:
        stats["lunch_notes"] = lunch_notes

    return score, timeline, warnings, stats


def order_result(
    score: float,
    timeline: List[Dict[str, Any]],
    warnings: List[str],
    stats: Dict[str, Any],
) -> Dict[str, Any]:
    order = [event["meeting_id"] for event in timeline if event.get("meeting_id")]
    return {
        "best_order": order,
        "score": round(score, 2),
        "warnings": warnings,
        "stats": stats,
        "timeline": timeline,
    }


def render_markdown(result: Dict[str, Any], stops: Dict[str, Stop]) -> str:
    rows = [
        f"Checked orders: {result['checked_orders']}",
        f"Best order: {' -> '.join(result['best']['best_order'])}",
        "",
        "| Time | Plan | Address/contact | Transport | Status | Notes |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for event in result["best"]["timeline"]:
        if event.get("event") == "end_transfer":
            rows.append(
                f"| {event['depart']}-{event['arrive']} | End transfer | {event.get('location','')} | {event['mode']} {event['travel_minutes']} min | - | walking {event.get('walking_m',0)}m |"
            )
            continue
        status = "fixed" if event.get("fixed") else "flexible"
        contact = event.get("contact") or ""
        rows.append(
            f"| {event['start']}-{event['end']} | {event['name']} | {event.get('address','')} {contact} | "
            f"{event['depart']} depart, {event['mode']} {event['travel_minutes']} min | {status} | "
            f"buffer {event.get('wait_or_buffer_minutes',0)} min, walking {event.get('walking_m',0)}m |"
        )
    rows.append("")
    rows.append("Stats: " + json.dumps(result["best"]["stats"], ensure_ascii=False))
    if result["best"]["warnings"]:
        rows.append("Warnings: " + "；".join(result["best"]["warnings"]))
    if result.get("alternatives"):
        rows.append("")
        rows.append("Alternatives:")
        for alt in result["alternatives"]:
            rows.append(f"- {' -> '.join(alt['best_order'])}: score {alt['score']}, warnings {len(alt['warnings'])}")
    return "\n".join(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Optimize a roadshow route using live Amap leg estimates.")
    parser.add_argument("input_json", help="Structured itinerary JSON")
    parser.add_argument("--pre-buffer", type=int, default=10, help="Minutes before flexible meetings")
    parser.add_argument("--post-buffer", type=int, default=5, help="Minutes after each meeting")
    parser.add_argument("--pre-fixed-buffer", type=int, default=15, help="Minutes to arrive before fixed meetings")
    parser.add_argument("--preference", default="", help="efficiency, energy, taxi, subway, or hybrid; overrides JSON")
    parser.add_argument("--max-permutations", type=int, default=40320, help="Safety cap; 40320 covers 8 meetings")
    parser.add_argument("--pause", type=float, default=0.05, help="Seconds to pause between Amap requests")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    args = parser.parse_args()

    amap_key = os.environ.get("AMAP_KEY") or os.environ.get("AMAP_API_KEY")
    if not amap_key:
        raise SystemExit("Missing AMAP_KEY/AMAP_API_KEY. Configure a Gaode/Amap Web service key first.")

    with open(args.input_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    city = str(data.get("city") or "")
    if not city:
        raise SystemExit("Input JSON must include city, e.g. 北京")
    start = resolve_stop(data.get("start") or {"id": "START", "name": "START"}, city, amap_key, "START")
    meetings = [resolve_meeting(item, city, amap_key, idx + 1) for idx, item in enumerate(data.get("meetings", []))]
    if not meetings:
        raise SystemExit("Input JSON must include a non-empty meetings array")

    end_stop: Optional[Stop] = None
    if isinstance(data.get("end"), dict) and data["end"].get("id"):
        end_stop = resolve_stop(data["end"], city, amap_key, "END")
        data["end"] = asdict(end_stop)

    data["start"] = asdict(start)
    data["meetings"] = [asdict(m) for m in meetings]
    stops: List[Stop] = [start, *meetings]
    if end_stop:
        stops.append(end_stop)
    matrix = build_matrix(stops, city, amap_key, args.pause)

    results: List[Tuple[float, List[Dict[str, Any]], List[str], Dict[str, Any]]] = []
    checked = 0
    for order in candidate_orders(meetings, args.max_permutations):
        checked += 1
        results.append(simulate(order, data, matrix, args))

    results.sort(key=lambda item: item[0])
    best = order_result(*results[0])
    alternatives = [order_result(*item) for item in results[1:4]]
    payload = {
        "checked_orders": checked,
        "city": city,
        "start": asdict(start),
        "stops": {stop.id: asdict(stop) for stop in stops},
        "matrix": {
            key: {mode: asdict(leg) for mode, leg in options.items()}
            for key, options in matrix.items()
        },
        "best": best,
        "alternatives": alternatives,
        "note": "Amap supplies single-leg estimates; this script enumerates and scores whole-day orders.",
    }

    if args.format == "markdown":
        print(render_markdown(payload, {stop.id: stop for stop in stops}))
    else:
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
