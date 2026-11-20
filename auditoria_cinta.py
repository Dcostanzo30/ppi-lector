#!/usr/bin/env python3
"""Read-only PPI tape audit and bounded raw-schema sampling."""
import argparse
import collections
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

def walk(obj, path="$", parents=None):
    parents = parents or []
    if isinstance(obj, dict):
        yield obj, path, parents
        for k, v in obj.items():
            yield from walk(v, f"{path}.{k}", parents + [k])
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f"{path}[{i}]", parents)

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
    first_recv = last_recv = None
    parse_fail = 0
    first_target = last_target = None
    samples = []
    overlap_samples = []
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
            matches = []
            for d, pth, parents in walk(obj):
                ticker = first(d, "Ticker", "Symbol", "Instrument")
                if ticker is None:
                    continue
                ticker = str(ticker).upper()
                tickers[ticker] += 1
                if ticker != target:
                    continue
                matches.append((d, pth, parents))
                stats["target_objects"] += 1
                event = first(d, "Date", "Timestamp", "Time")
                if event is not None:
                    event = str(event)
                    first_target = first_target or event
                    last_target = event
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
            if matches:
                sample = {
                    "line": n,
                    "received_time": recv,
                    "target_paths": [m[1] for m in matches[:8]],
                    "target_objects": [m[0] for m in matches[:8]],
                    "root_message": obj,
                }
                if len(samples) < 8:
                    samples.append(sample)
                if recv and "T13:" in recv and len(overlap_samples) < 12:
                    hhmm = recv[11:16]
                    if "13:25" <= hhmm <= "13:50":
                        overlap_samples.append(sample)
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
        "schema_samples_first": samples,
        "schema_samples_overlap": overlap_samples,
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
            "Recursive object counts remain provisional; schema_samples expose the enclosing raw message for validation.",
            "The two files are reported separately; no records are deleted or deduplicated.",
            "schema_samples_overlap contains received-time samples from 13:25-13:50 when present."
        ]
    }
    pathlib.Path(a.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"date":a.date,"ticker":a.ticker,"audit_status":result["audit_status"],"errors":errors}, ensure_ascii=False, indent=2))
    if errors:
        sys.exit(2)

if __name__ == "__main__":
    main()
