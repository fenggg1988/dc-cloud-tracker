# -*- coding: utf-8 -*-
"""
美国数据中心建设 & 云企融资监控 - 每日新闻/行情抓取
自动部分：
1) Google News RSS 抓取相关新闻头条 → data/news.json
2) Yahoo Finance 抓取六大公司股价日线（近6个月）→ data/market.json
3) FRED 抓取美债/公司债收益率与信用利差（市场级）→ data/market.json
调研型数据（发债利率明细、CDS 关键点位、GPU 台账等）
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
MARKET_FILE = BASE / "data" / "market.json"
MAX_KEEP = 120  # 最多保留条数

# 监控的六家公司（美股代码 → 中文名）
TICKERS = {
    "MSFT": "微软", "AMZN": "亚马逊", "GOOGL": "谷歌",
    "META": "Meta", "ORCL": "甲骨文", "CRWV": "CoreWeave",
}

# FRED 序列：市场级债券利率与信用利差
FRED_SERIES = {
    "DGS10": "10年期美债收益率(%)",
    "BAA": "穆迪Baa公司债收益率(%)",
    "BAMLH0A0HYM2": "美债高收益利差HY OAS(bp)",
    "BAMLC0A0CM": "投资级公司债利差IG OAS(bp)",
}
FRED_START = "2025-01-01"  # 走势起点

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


def fetch_stocks(session: requests.Session):
    """Yahoo Finance v8 chart API：日线收盘价（近6个月）+ 最新价。"""
    stocks = {}
    for sym, name in TICKERS.items():
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
        params = {"range": "6mo", "interval": "1d"}
        try:
            r = session.get(url, params=params, headers=HEADERS, timeout=30)
            r.raise_for_status()
            res = r.json()["chart"]["result"][0]
            meta = res.get("meta", {})
            ts = res.get("timestamp") or []
            closes = (res.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
            rows = [
                {"date": datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d"), "close": round(c, 2)}
                for t, c in zip(ts, closes) if c is not None
            ]
            stocks[sym] = {
                "name": name,
                "currency": meta.get("currency", "USD"),
                "last_price": meta.get("regularMarketPrice"),
                "last_change_pct": meta.get("regularMarketChangePercent"),
                "history": rows,
            }
            print(f"[ok] {sym}: {len(rows)} bars, last {rows[-1]['close'] if rows else meta.get('regularMarketPrice')}")
        except Exception as e:
            print(f"[warn] stock failed: {sym} -> {e}")
        time.sleep(1.0)
    return stocks


def fetch_fred(session: requests.Session):
    """FRED fredgraph.csv：美债/公司债收益率与信用利差日线。"""
    out = {}
    fred_session = requests.Session()  # 独立会话，避免与 Yahoo 连接复用问题
    fred_session.headers.update({"User-Agent": HEADERS["User-Agent"]})
    for sid, label in FRED_SERIES.items():
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv"
        params = {"id": sid, "cosd": FRED_START}
        rows = []
        for attempt in range(3):
            try:
                r = fred_session.get(url, params=params, timeout=60)
                r.raise_for_status()
                rows = []
                lines = r.text.strip().splitlines()
                for line in lines[1:]:
                    parts = line.split(",")
                    if len(parts) >= 2 and parts[1] not in (".", ""):
                        rows.append({"date": parts[0], "value": float(parts[1])})
                break
            except Exception as e:
                print(f"[warn] fred attempt {attempt+1} failed: {sid} -> {e}")
                # requests 被 FRED 限流/超时时用 curl 兜底
                try:
                    import subprocess
                    full = f"{url}?id={sid}&cosd={FRED_START}"
                    cp = subprocess.run(["curl", "-s", "--max-time", "60", full],
                                        capture_output=True, text=True, timeout=90)
                    if cp.returncode == 0 and "," in cp.stdout:
                        rows = []
                        for line in cp.stdout.strip().splitlines()[1:]:
                            parts = line.split(",")
                            if len(parts) >= 2 and parts[1] not in (".", ""):
                                rows.append({"date": parts[0], "value": float(parts[1])})
                        if rows:
                            print(f"[ok] fred via curl: {sid}")
                            break
                except Exception as e2:
                    print(f"[warn] fred curl fallback failed: {sid} -> {e2}")
                time.sleep(3)
        if rows:
            out[sid] = {"label": label, "history": rows}
            print(f"[ok] FRED {sid}: {len(rows)} obs")
        else:
            print(f"[warn] fred failed after retries: {sid}")
        time.sleep(0.5)
    return out


def update_market():
    session = requests.Session()
    stocks = fetch_stocks(session)
    fred = fetch_fred(session)
    if not stocks and not fred:
        print("[warn] market data all failed, keep old file")
        return
    prev = {}
    if MARKET_FILE.exists():
        try:
            prev = json.loads(MARKET_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    out = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "stocks": stocks or prev.get("stocks", {}),
        "fred": fred or prev.get("fred", {}),
    }
    MARKET_FILE.parent.mkdir(parents=True, exist_ok=True)
    MARKET_FILE.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"[ok] market -> {MARKET_FILE}")


def main():
    update_market()
    fetch_news()


def fetch_news():
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
