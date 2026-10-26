# -*- coding: utf-8 -*-
"""
美国数据中心建设 & 云企融资监控 - 每日新闻抓取
自动部分：通过 Google News RSS 抓取与数据中心建设/云企融资相关的新闻头条，
输出 data/news.json（供看板展示）。调研型数据（发债利率、GPU 台账等）
存于 data/curated.json，由 AI 调研后手动/按需更新。
"""
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from email.utils import parsedate_to_datetime

import requests

BASE = Path(__file__).resolve().parent
NEWS_FILE = BASE / "data" / "news.json"
MAX_KEEP = 120  # 最多保留条数

# 关键词查询：覆盖建设进度 / 融资发债 / GPU 采购 / 资本支出
QUERIES = [
    "hyperscaler capex data center",
    "AI data center bond issuance",
    "data center financing billion",
    "data center construction gigawatt",
    "Microsoft OR Amazon OR Google OR Meta data center capex",
    "Oracle CoreWeave data center debt",
    "GPU purchase Microsoft Amazon Meta Google Oracle",
    "Stargate OpenAI data center progress",
    "AI infrastructure funding gap",
]

HEADERS = {"User-Agent": "Mozilla/5.0 (dc-cloud-tracker/1.0)"}

STOP_RE = re.compile(
    r"(招聘|Salary|job|Job|hiring|Hiring|cours|Coursera|Udemy|degree|Degree|tutorial|Tutorial)",
)


def fetch_query(session: requests.Session, query: str):
    url = "https://news.google.com/rss/search"
    params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    try:
        r = session.get(url, params=params, headers=HEADERS, timeout=30)
        r.raise_for_status()
    except Exception as e:
        print(f"[warn] query failed: {query} -> {e}")
        return []
    items = []
    try:
        root = ET.fromstring(r.content)
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub = (item.findtext("pubDate") or "").strip()
            source_el = item.find("source")
            source = source_el.text.strip() if source_el is not None and source_el.text else ""
            if not title:
                continue
            dt = None
            if pub:
                try:
                    dt = parsedate_to_datetime(pub).astimezone(timezone.utc)
                except Exception:
                    dt = None
            items.append({
                "title": title,
                "source": source,
                "link": link,
                "published": dt.strftime("%Y-%m-%d") if dt else "",
                "ts": dt.isoformat() if dt else "",
            })
    except ET.ParseError as e:
        print(f"[warn] parse failed: {query} -> {e}")
    return items


def main():
    session = requests.Session()
    all_items = {}
    for q in QUERIES:
        for it in fetch_query(session, q):
            key = it["title"]
            if key not in all_items:
                it["queries"] = [q]
                all_items[key] = it
            else:
                all_items[key]["queries"].append(q)
        time.sleep(1.0)

    # 过滤招聘/课程类噪音
    items = [it for it in all_items.values() if not STOP_RE.search(it["title"])]
    # 按时间倒序
    items.sort(key=lambda x: x.get("ts") or "", reverse=True)
    items = items[:MAX_KEEP]

    out = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "count": len(items),
        "items": items,
    }
    NEWS_FILE.parent.mkdir(parents=True, exist_ok=True)
    NEWS_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] {len(items)} news items -> {NEWS_FILE}")


if __name__ == "__main__":
    main()
