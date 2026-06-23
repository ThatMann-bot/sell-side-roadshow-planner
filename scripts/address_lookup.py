#!/usr/bin/env python3
"""Look up live map candidates for roadshow institution addresses.

This script intentionally does not contain sample address fixtures. Screenshots,
copied examples, and stale notes may be anonymized or outdated, so every run
should query a live map provider and then be checked against official sites.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List


DEFAULT_TIMEOUT = 12


GENERIC_SUFFIXES = [
    "基金管理有限公司",
    "基金有限公司",
    "证券股份有限公司",
    "证券有限公司",
    "资产管理有限公司",
    "投资管理有限公司",
    "资本管理有限公司",
    "管理有限公司",
    "有限公司",
    "股份有限公司",
    "基金",
    "证券",
    "资管",
    "资本",
]


@dataclass
class Candidate:
    input_name: str
    candidate_name: str
    address: str
    city: str = ""
    district: str = ""
    source: str = ""
    confidence: float = 0.0
    location: str = ""
    note: str = ""


def normalize_name(name: str) -> str:
    text = re.sub(r"\s+", "", name or "")
    text = text.replace("（", "(").replace("）", ")")
    text = re.sub(r"\(.*?\)", "", text)
    for suffix in GENERIC_SUFFIXES:
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    return text


def entity_type_tokens(text: str) -> set[str]:
    tokens = set()
    for token in ("基金", "证券", "资本", "资管", "资产", "银行", "保险", "信托", "期货"):
        if token in (text or ""):
            tokens.add(token)
    # 资产管理 and 资管 are often synonyms in this context.
    if "资产" in tokens:
        tokens.add("资管")
    return tokens


def http_json(url: str) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "sell-side-roadshow-planner/2.0",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
        body = response.read().decode("utf-8", errors="replace")
    return json.loads(body)


def score_candidate(query: str, name: str, address: str, base: float = 0.45) -> float:
    q = normalize_name(query)
    n = normalize_name(name)
    score = base
    if q and q == n:
        score += 0.35
    elif q and (q in n or n in q):
        score += 0.25
    if any(token in name or token in address for token in ("基金", "证券", "资产", "资本", "金融", "投资")):
        score += 0.08
    if "北京" in address or "北京市" in address:
        score += 0.05
    q_types = entity_type_tokens(query)
    n_types = entity_type_tokens(name)
    if q_types and n_types and not (q_types & n_types):
        score -= 0.25
    if "资本" in q_types and "资本" not in n_types:
        score -= 0.2
    if "证券" in n_types and "证券" not in q_types:
        score -= 0.12
    if "基金" in q_types and "基金" not in n_types:
        score -= 0.15
    return min(score, 0.92)


def lookup_amap(name: str, city: str, key: str, limit: int) -> List[Candidate]:
    params = {
        "key": key,
        "keywords": name,
        "city": city,
        "citylimit": "true" if city else "false",
        "offset": str(max(limit, 1)),
        "page": "1",
        "extensions": "all",
    }
    url = "https://restapi.amap.com/v3/place/text?" + urllib.parse.urlencode(params)
    data = http_json(url)
    results: List[Candidate] = []
    if data.get("status") != "1":
        return [
            Candidate(
                input_name=name,
                candidate_name="",
                address="",
                city=city,
                source="amap_error",
                note=str(data.get("info") or data),
            )
        ]
    for poi in data.get("pois", [])[:limit]:
        pname = str(poi.get("name", ""))
        address = poi.get("address", "")
        if isinstance(address, list):
            address = ""
        district = str(poi.get("adname", ""))
        pcity = str(poi.get("cityname", city))
        loc = str(poi.get("location", ""))
        formatted = "".join(part for part in [pcity, district, str(address)] if part)
        results.append(
            Candidate(
                input_name=name,
                candidate_name=pname,
                address=formatted or str(address),
                city=pcity,
                district=district,
                source="amap",
                confidence=score_candidate(name, pname, formatted),
                location=loc,
                note=str(poi.get("type", "")),
            )
        )
    return results


def lookup_baidu(name: str, city: str, key: str, limit: int) -> List[Candidate]:
    params = {
        "query": name,
        "region": city or "全国",
        "output": "json",
        "ak": key,
        "page_size": str(max(min(limit, 20), 1)),
        "page_num": "0",
    }
    url = "https://api.map.baidu.com/place/v2/search?" + urllib.parse.urlencode(params)
    data = http_json(url)
    results: List[Candidate] = []
    if data.get("status") not in (0, "0"):
        return [
            Candidate(
                input_name=name,
                candidate_name="",
                address="",
                city=city,
                source="baidu_error",
                note=str(data.get("message") or data),
            )
        ]
    for item in data.get("results", [])[:limit]:
        pname = str(item.get("name", ""))
        address = str(item.get("address", ""))
        area = str(item.get("area", ""))
        location = item.get("location") or {}
        loc = ""
        if isinstance(location, dict) and "lng" in location and "lat" in location:
            loc = f"{location.get('lng')},{location.get('lat')}"
        results.append(
            Candidate(
                input_name=name,
                candidate_name=pname,
                address=address,
                city=city,
                district=area,
                source="baidu",
                confidence=score_candidate(name, pname, address),
                location=loc,
                note=str(item.get("tag", "")),
            )
        )
    return results


def lookup_tencent(name: str, city: str, key: str, limit: int) -> List[Candidate]:
    boundary = f"region({city},0)" if city else "region(中国,0)"
    params = {
        "keyword": name,
        "boundary": boundary,
        "key": key,
        "page_size": str(max(min(limit, 20), 1)),
        "page_index": "1",
    }
    url = "https://apis.map.qq.com/ws/place/v1/search?" + urllib.parse.urlencode(params)
    data = http_json(url)
    results: List[Candidate] = []
    if data.get("status") not in (0, "0"):
        return [
            Candidate(
                input_name=name,
                candidate_name="",
                address="",
                city=city,
                source="tencent_error",
                note=str(data.get("message") or data),
            )
        ]
    for item in data.get("data", [])[:limit]:
        pname = str(item.get("title", ""))
        address = str(item.get("address", ""))
        ad_info = item.get("ad_info") or {}
        district = str(ad_info.get("district", ""))
        city_name = str(ad_info.get("city", city))
        location = item.get("location") or {}
        loc = ""
        if isinstance(location, dict) and "lng" in location and "lat" in location:
            loc = f"{location.get('lng')},{location.get('lat')}"
        results.append(
            Candidate(
                input_name=name,
                candidate_name=pname,
                address=address,
                city=city_name,
                district=district,
                source="tencent",
                confidence=score_candidate(name, pname, address),
                location=loc,
                note=str(item.get("category", "")),
            )
        )
    return results


def live_lookup(name: str, city: str, provider: str, limit: int) -> List[Candidate]:
    provider = provider.lower()
    lookups = []
    amap_key = os.getenv("AMAP_KEY") or os.getenv("AMAP_API_KEY")
    baidu_key = os.getenv("BAIDU_MAP_AK")
    tencent_key = os.getenv("TENCENT_MAP_KEY") or os.getenv("QQ_MAP_KEY")

    if provider in ("auto", "amap") and amap_key:
        lookups.append(lambda: lookup_amap(name, city, amap_key, limit))
    if provider in ("auto", "baidu") and baidu_key:
        lookups.append(lambda: lookup_baidu(name, city, baidu_key, limit))
    if provider in ("auto", "tencent") and tencent_key:
        lookups.append(lambda: lookup_tencent(name, city, tencent_key, limit))

    if not lookups:
        return [
            Candidate(
                input_name=name,
                candidate_name="",
                address="",
                city=city,
                source="missing_map_key",
                note="未配置地图API Key。请配置 AMAP_KEY/AMAP_API_KEY，或显式配置 BAIDU_MAP_AK / TENCENT_MAP_KEY。",
            )
        ]

    results: List[Candidate] = []
    for func in lookups:
        try:
            results.extend(func())
        except Exception as exc:
            results.append(
                Candidate(
                    input_name=name,
                    candidate_name="",
                    address="",
                    city=city,
                    source="provider_error",
                    note=str(exc),
                )
            )
    return results


def dedupe(candidates: Iterable[Candidate]) -> List[Candidate]:
    seen = set()
    output = []
    for cand in candidates:
        key = (normalize_name(cand.candidate_name), re.sub(r"\s+", "", cand.address))
        if key in seen:
            continue
        seen.add(key)
        output.append(cand)
    return output


def lookup_one(name: str, city: str, provider: str, limit: int) -> List[Candidate]:
    candidates = live_lookup(name, city, provider, limit)
    candidates = [c for c in candidates if c.candidate_name or c.address or c.note]
    if not candidates:
        candidates.append(
            Candidate(
                input_name=name,
                candidate_name="",
                address="",
                city=city,
                source="unresolved",
                confidence=0.0,
                note="地图API未返回候选；请改用全称、补充主体类型，或向销售/买方确认。",
            )
        )
    return dedupe(candidates)[:limit]


def extract_names_from_input(path: str) -> tuple[str, List[str]]:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "", lines

    city = str(data.get("city", ""))
    if isinstance(data.get("institutions"), list):
        return city, [str(x) for x in data["institutions"]]
    names = []
    for item in data.get("meetings", []):
        if isinstance(item, dict):
            names.append(str(item.get("name") or item.get("institution") or item.get("id") or ""))
    return city, [n for n in names if n]


def render_markdown(results: Dict[str, List[Candidate]]) -> str:
    rows = [
        "| 输入机构 | 候选名称 | 候选地址 | 行政区 | 来源 | 置信度 | 备注 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name, candidates in results.items():
        for idx, cand in enumerate(candidates):
            label = name if idx == 0 else ""
            confidence = f"{cand.confidence:.2f}" if cand.confidence else ""
            rows.append(
                "| "
                + " | ".join(
                    [
                        label,
                        cand.candidate_name or "待人工确认",
                        cand.address or "待人工确认",
                        cand.district or "",
                        cand.source,
                        confidence,
                        cand.note.replace("|", "/"),
                    ]
                )
                + " |"
            )
    return "\n".join(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Look up live map address candidates for roadshow institutions.")
    parser.add_argument("names", nargs="*", help="Institution names, e.g. 机构A 机构B")
    parser.add_argument("--city", default="", help="City or region, e.g. 北京")
    parser.add_argument("--input", help="JSON or newline-delimited text file with institution names")
    parser.add_argument("--provider", default="auto", choices=["auto", "amap", "baidu", "tencent"], help="Map provider")
    parser.add_argument("--limit", type=int, default=3, help="Candidates per institution")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    args = parser.parse_args()

    city = args.city
    names = list(args.names)
    if args.input:
        input_city, input_names = extract_names_from_input(args.input)
        city = city or input_city
        names.extend(input_names)

    if not names:
        parser.error("Provide at least one institution name or --input file")

    results = {name: lookup_one(name, city, args.provider, args.limit) for name in names}

    if args.format == "json":
        payload = {name: [asdict(c) for c in candidates] for name, candidates in results.items()}
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        print(render_markdown(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
