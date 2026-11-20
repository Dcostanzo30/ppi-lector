#!/usr/bin/env python3
"""Read-only integrity and GGAL tape audit. Never rewrites source tapes."""
import argparse
import collections
import datetime as dt
import gzip
import json
import pathlib
import sys

def parse_line(line):
    line = line.rstrip(b"\r\n")
    if not line:
        return None, None
    try:
        stamp, payload = line.split(b"\t", 1)
        received = stamp.decode("utf-8", "replace")
    except ValueError:
        received, payload = None, line
    raw = payload.decode("utf-8", "replace").strip()
    try:
        obj = json.loads(raw)
    except Exception:
        try:
            obj = json.loads(raw.replace('""', '"'))
        except Exception:
            return received, None
    if isinstance(obj, str):
        try:
            obj = json.loads(obj)
        except Exception:
            pass
    return received, obj

def walk(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v)

def first(d, *keys):
    low = {str(k).lower(): v for k, v in d.items()}
    for k in keys:
        if k.lower() in low:
            return low[k.lower()]
    return None

def truth(v):
    return v is True or str(v).lower() == "true"

def inspect(path, target):
    stats = collections.Counter()
    tickers = collections.Counter()
    target_trades = []
    target_books = 0
    first_event = last_event = None
    first_recv = last_recv = None
    parse_fail = 0
    first_target = last_target = None
    # gzip.open validates stream trailer/CRC on complete iteration.
    with gzip.open(path, "rb") as f:
        for n, line in enumerate(f, 1):
            stats["lines"] += 1
            recv, obj = parse_line(line)
            if recv:
                first_recv = first_recv or recv
                last_recv = recv
            if obj is None:
                parse_fail += 1
                continue
            stats["json_lines"] += 1
            for d in walk(obj):
                ticker = first(d, "Ticker", "Symbol", "Instrument")
                if ticker is None:
                    continue
                ticker = str(ticker).upper()
                tickers[ticker] += 1
                if ticker != target:
                    continue
                stats["target_objects"] += 1
                event = first(d, "Date", "Timestamp", "Time")
                if event is not None:
                    event = str(event)
                    first_target = first_target or event
                    last_target = event
                    first_event = first_event or event
                    last_event = event
                if truth(first(d, "Trade")):
                    stats["target_trades"] += 1
                    target_trades.append({
                        "event_time": event,
                        "received_time": recv,
                        "price": first(d, "Price"),
                        "volume_amount": first(d, "VolumeAmount"),
                        "volume_currency": first(d, "VolumeCurrency"),
                        "volume_total_amount": first(d, "VolumeTotalAmount"),
                    })
                elif first(d, "Bids") is not None or first(d, "Offers") is not None:
                    target_books += 1
    stats["parse_fail"] = parse_fail
    return {
        "file": str(path),
        "bytes": path.stat().st_size,
        "gzip_integrity": "OK",
        "lines": stats["lines"],
        "json_lines": stats["json_lines"],
        "parse_fail": parse_fail,
        "received_first": first_recv,
        "received_last": last_recv,
        "ticker_message_counts_top20": tickers.most_common(20),
        "target": target,
        "target_objects": stats["target_objects"],
        "target_trades": stats["target_trades"],
        "target_book_events": target_books,
        "target_event_first": first_target,
        "target_event_last": last_target,
        "target_trade_sample_first": target_trades[:3],
        "target_trade_sample_last": target_trades[-3:],
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--ticker", default="GGAL")
    ap.add_argument("--morning", required=True)
    ap.add_argument("--afternoon", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    reports = []
    errors = []
    for name in (a.morning, a.afternoon):
        try:
            reports.append(inspect(pathlib.Path(name), a.ticker.upper()))
        except Exception as e:
            errors.append({"file": name, "error": f"{type(e).__name__}: {e}"})
    result = {
        "date": a.date, "ticker": a.ticker.upper(),
        "audit_status": "PASS" if len(reports) == 2 and not errors and all(x["parse_fail"] == 0 for x in reports) else "REVIEW",
        "files": reports, "errors": errors,
        "notes": [
            "gzip_integrity=OK means the entire gzip stream was read and its trailer/CRC validated.",
            "Message/object counts are not trade counts; inspect the raw schema before interpreting nested-object counts.",
            "The two files are reported separately; no records are deleted or deduplicated.",
            "Event-time field selection is heuristic and requires schema confirmation."
        ]
    }
    pathlib.Path(a.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if errors:
        sys.exit(2)

if __name__ == "__main__":
    main()
