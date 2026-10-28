"""Scheduled / Batch Data Pipeline (renamed from "Real-time" on 2026-10-28:
the ingestion here is scheduled/batch, not streaming, so the old name
was misleading and has been removed from code and README).

Sources: sales.csv (or a synthetic CSV), Open-Meteo weather (Wichita),
JSONPlaceholder posts (public API). Live sources are optional:
--no-live skips them so runs are deterministic offline.
Transforms: dedupe by order_id, drop missing-amount rows, aggregate
daily revenue, count posts by user.
Quality gates: clean duplicates == 0, clean rows > 0, no null amounts
in the clean set.
Alerts: quality-gate failure OR daily revenue drop >30% vs previous day.
Delivery: if ALERT_WEBHOOK_URL is set, alerts are POSTed to it;
otherwise they fall back to alerts.json (file delivery, no one is
paged). See send_alerts() and test_alerts.py for the mock-endpoint test.
Outputs: warehouse db, dashboard JSON, dashboard.html (daily revenue
chart + quality-gate run history), run_history.jsonl (appended per run).
Idempotent re-runs: daily rows are INSERT OR REPLACE, so a re-run
produces identical daily revenue, never doubled revenue.
Tests: python3 test_pipeline.py ; python3 test_alerts.py
Large run: python3 pipeline_full.py --synthetic --rows 50000 --no-live
"""
import argparse
import csv
import json
import os
import sqlite3
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))


def fetch_weather():
    r = requests.get("https://api.open-meteo.com/v1/forecast?latitude=37.69&longitude=-97.34&current=temperature_2m",
                     timeout=20)
    r.raise_for_status()
    return r.json()["current"]


def fetch_posts():
    r = requests.get("https://jsonplaceholder.typicode.com/posts", timeout=20)
    r.raise_for_status()
    return r.json()[:20]


def clean_rows(rows):
    """Return (clean, duplicates_removed, null_rows_removed)."""
    seen, clean = set(), []
    dups = nulls = 0
    for r in rows:
        if not r["amount"]:
            nulls += 1
            continue
        if r["order_id"] in seen:
            dups += 1
            continue
        seen.add(r["order_id"])
        clean.append(r)
    return clean, dups, nulls


def send_alerts(alerts, webhook_url=None, alerts_path=None):
    """Deliver alerts. Returns a delivery record (no secrets are logged).

    If a webhook URL is given (or ALERT_WEBHOOK_URL is set), POST the
    alerts there and return the HTTP status. On any webhook failure, or
    when no webhook is configured, fall back to writing alerts.json.
    """
    url = webhook_url or os.environ.get("ALERT_WEBHOOK_URL")
    path = alerts_path or os.path.join(HERE, "alerts.json")
    if url:
        try:
            r = requests.post(url, json={"alerts": alerts}, timeout=10)
            if 200 <= r.status_code < 300:
                return {"sent": True, "via": "webhook", "status": r.status_code}
            # Webhook rejected it: fall through to the file fallback.
            json.dump(alerts, open(path, "w"), indent=2)
            return {"sent": False, "via": "file-fallback", "webhook_status": r.status_code}
        except Exception as e:  # noqa: BLE001 - fallback must never crash the run
            json.dump(alerts, open(path, "w"), indent=2)
            return {"sent": False, "via": "file-fallback", "error": type(e).__name__}
    json.dump(alerts, open(path, "w"), indent=2)
    return {"sent": False, "via": "file", "reason": "no webhook configured"}


def write_dashboard_html(out, history, path):
    daily = out["daily_revenue"]
    max_rev = max((d["revenue"] for d in daily), default=0) or 1
    bars = "".join(
        f"<div>{d['date']}: ${d['revenue']:.2f} ({d['orders']} orders) "
        f"<div style='background:#2563eb;height:14px;width:{d['revenue']/max_rev*100:.0f}%'></div></div>"
        for d in daily)
    hist = "".join(
        f"<tr><td>{h.get('run', '')}</td><td>{h.get('rows_in', '')}</td>"
        f"<td>{h.get('rows_out', '')}</td><td>{h.get('passed', '')}</td>"
        f"<td>{'; '.join(h.get('alerts', []))}</td></tr>"
        for h in history[-10:])
    html = (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>Scheduled Pipeline Dashboard</title></head><body>"
            f"<h1>Scheduled / Batch Pipeline Dashboard</h1>"
            f"<p>Status: {out['status']} | Rows in: {out['checks']['rows_in']} | "
            f"Rows out: {out['checks']['clean_rows']} | Duplicates removed: "
            f"{out['checks']['duplicates_removed']} | Null rows removed: "
            f"{out['checks']['null_rows_removed']} | Runtime: {out.get('runtime_seconds', 0)}s</p>"
            f"<h2>Daily revenue</h2>{bars}"
            f"<h2>Quality-gate run history (last 10)</h2><table border='1'>"
            f"<tr><th>Run</th><th>Rows in</th><th>Rows out</th><th>Passed</th><th>Alerts</th></tr>{hist}</table>"
            f"<pre>{json.dumps(out, indent=2)}</pre></body></html>")
    open(path, "w").write(html)


def run(input_csv=None, output_db=None, output_json=None, fetch_live=True,
        webhook_url=None, history_path=None):
    started = time.time()
    input_csv = input_csv or os.path.join(HERE, "sales.csv")
    output_db = output_db or os.path.join(HERE, "warehouse2.db")
    output_json = output_json or os.path.join(HERE, "dashboard_full.json")
    history_path = history_path or os.path.join(HERE, "run_history.jsonl")
    if os.path.exists(output_db):
        os.remove(output_db)
    c = sqlite3.connect(output_db)
    c.execute("CREATE TABLE daily_revenue(date TEXT PRIMARY KEY, revenue REAL, orders INTEGER)")
    c.execute("CREATE TABLE posts_by_user(user_id INTEGER PRIMARY KEY, posts INTEGER)")
    rows = list(csv.DictReader(open(input_csv)))
    clean, dups, nulls = clean_rows(rows)
    agg = {}
    for r in clean:
        d = agg.setdefault(r["order_date"], [0.0, 0])
        d[0] += float(r["amount"])
        d[1] += 1
    for d, (rev, n) in agg.items():
        c.execute("INSERT OR REPLACE INTO daily_revenue VALUES (?,?,?)", (d, round(rev, 2), n))
    posts, pu = [], {}
    if fetch_live:
        posts = fetch_posts()
        for p in posts:
            pu[p["userId"]] = pu.get(p["userId"], 0) + 1
        for uid, n in pu.items():
            c.execute("INSERT OR REPLACE INTO posts_by_user VALUES (?,?)", (uid, n))
    c.commit()
    daily = [{"date": r[0], "revenue": r[1], "orders": r[2]}
             for r in c.execute("SELECT * FROM daily_revenue ORDER BY date")]
    checks = {"raw_rows": len(rows), "rows_in": len(rows), "clean_rows": len(clean),
              "duplicates_removed": dups, "null_rows_removed": nulls,
              "clean_duplicates": len(clean) - len(set(r["order_id"] for r in clean)),
              "passed": len(clean) > 0 and len(set(r["order_id"] for r in clean)) == len(clean)}
    alerts = []
    if not checks["passed"]:
        alerts.append("QUALITY GATE FAILED")
    if len(daily) >= 2 and daily[-1]["revenue"] < daily[-2]["revenue"] * 0.7:
        alerts.append(f"Revenue drop: {daily[-2]['revenue']} -> {daily[-1]['revenue']}")
    delivery = send_alerts(alerts, webhook_url=webhook_url)
    weather = fetch_weather() if fetch_live else None
    out = {"daily_revenue": daily, "posts_by_user": pu, "weather": weather,
           "checks": checks, "alerts": alerts, "alert_delivery": delivery,
           "status": "OK" if checks["passed"] else "FAILED",
           "runtime_seconds": round(time.time() - started, 3),
           "total_revenue": round(sum(d["revenue"] for d in daily), 2)}
    json.dump(out, open(output_json, "w"), indent=2)
    record = {"run": time.strftime("%Y-%m-%d %H:%M:%S"), "rows_in": len(rows),
              "rows_out": len(clean), "passed": checks["passed"], "alerts": alerts}
    with open(history_path, "a") as f:
        f.write(json.dumps(record) + "\n")
    history = []
    for line in open(history_path):
        try:
            history.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    write_dashboard_html(out, history, os.path.join(HERE, "dashboard.html"))
    print(json.dumps(out, indent=2))
    return 0 if checks["passed"] else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=None)
    ap.add_argument("--output-db", default=None)
    ap.add_argument("--output-json", default=None)
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--rows", type=int, default=50000)
    ap.add_argument("--no-live", action="store_true")
    a = ap.parse_args()
    inp = a.input
    if a.synthetic:
        from generate_sales import generate
        inp = os.path.join(HERE, "sales_large.csv")
        print(generate(inp, a.rows))
        a.output_db = a.output_db or os.path.join(HERE, "warehouse_large.db")
        a.output_json = a.output_json or os.path.join(HERE, "dashboard_large.json")
    raise SystemExit(run(input_csv=inp, output_db=a.output_db, output_json=a.output_json,
                         fetch_live=not a.no_live))
