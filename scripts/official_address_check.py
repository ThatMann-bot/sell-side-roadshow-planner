#!/usr/bin/env python3
"""Extract and compare address snippets from an official web page.

Use this after live map lookup when the agent has found a likely official
company page, especially a "联系我们", "公司概况", or legal footer page.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.request
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from typing import List


DEFAULT_TIMEOUT = 15


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.parts: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"script", "style", "noscript"}:
            self.skip += 1
        if tag.lower() in {"p", "div", "br", "li", "tr", "td", "section", "footer"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag.lower() in {"script", "style", "noscript"} and self.skip:
            self.skip -= 1
        if tag.lower() in {"p", "div", "li", "tr", "section", "footer"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


@dataclass
class OfficialAddressCheck:
    url: str
    candidate_address: str
    official_snippets: List[str]
    matched: bool
    score: float
    note: str


def fetch_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "sell-side-roadshow-planner/2.0",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
        raw = response.read()
        encoding = response.headers.get_content_charset() or "utf-8"
    parser = TextExtractor()
    parser.feed(raw.decode(encoding, errors="replace"))
    text = html.unescape("".join(parser.parts))
    return re.sub(r"[ \t\r\f\v]+", " ", text)


def extract_address_snippets(text: str) -> List[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    pattern = re.compile(
        r"(?:办公地址|注册地址|联系地址|公司地址|地址|Address)[:：]?\s*"
        r"([^。；;\n]{6,80}(?:楼|层|座|室|号|大厦|中心|广场|园区|building|floor)?)",
        re.IGNORECASE,
    )
    snippets: List[str] = []
    for line in lines:
        for match in pattern.finditer(line):
            snippet = match.group(0).strip()
            if snippet not in snippets:
                snippets.append(snippet)
        if len(snippets) >= 10:
            break
    if not snippets:
        for line in lines:
            if any(token in line for token in ("北京市", "上海市", "深圳市", "广州市", "地址", "大厦", "中心")):
                if len(line) <= 120 and line not in snippets:
                    snippets.append(line)
            if len(snippets) >= 10:
                break
    return snippets


def normalize_address(text: str) -> str:
    text = re.sub(r"\s+", "", text or "")
    text = text.replace("（", "(").replace("）", ")")
    text = re.sub(r"[，,。；;:：()（）\-—_]", "", text)
    return text


def similarity(candidate: str, snippet: str) -> float:
    cand = normalize_address(candidate)
    snip = normalize_address(snippet)
    if not cand or not snip:
        return 0.0
    if cand in snip or snip in cand:
        return 1.0
    cand_tokens = set(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", cand))
    snip_tokens = set(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", snip))
    if not cand_tokens or not snip_tokens:
        return 0.0
    return len(cand_tokens & snip_tokens) / len(cand_tokens | snip_tokens)


def check(url: str, candidate: str) -> OfficialAddressCheck:
    text = fetch_text(url)
    snippets = extract_address_snippets(text)
    scores = [similarity(candidate, snippet) for snippet in snippets]
    best = max(scores) if scores else 0.0
    return OfficialAddressCheck(
        url=url,
        candidate_address=candidate,
        official_snippets=snippets,
        matched=best >= 0.35,
        score=round(best, 3),
        note="matched official page" if best >= 0.35 else "no strong address match; inspect snippets manually",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Check a map candidate address against an official page.")
    parser.add_argument("--url", required=True, help="Official company/contact page URL")
    parser.add_argument("--candidate", required=True, help="Candidate address from map provider")
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown")
    args = parser.parse_args()

    result = check(args.url, args.candidate)
    if args.format == "json":
        json.dump(asdict(result), sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"Official URL: {result.url}")
        print(f"Candidate: {result.candidate_address}")
        print(f"Matched: {result.matched} (score {result.score})")
        print(f"Note: {result.note}")
        print("Official snippets:")
        for snippet in result.official_snippets:
            print(f"- {snippet}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
