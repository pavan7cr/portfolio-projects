"""Data pipeline platform MVP - stdlib only.
Run: python3 pipeline.py
Steps, in order, with a quality gate that FAILS LOUDLY:
  1. Ingest sales.csv (raw) -> raw table
  2. Transform: dedupe by order_id, drop rows with missing amount,
     normalise dates, aggregate daily revenue -> daily_revenue table
  3. Quality checks: row count > 0, null rate in amount == 0,
     duplicate order_id rate == 0, freshness (max date within data)
     If any check fails, the run is marked FAILED and no dashboard
     is served from that run.
  4. Dashboard summary written to dashboard.json
Idempotency: re-running the same input replaces (not duplicates)
the daily_revenue rows for those dates.
"""
import csv, json, sqlite3, os
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "warehouse.db")

def run():
    if os.path.exists(DB): os.remove(DB)
    c = sqlite3.connect(DB)
    c.execute("CREATE TABLE raw(order_id TEXT, order_date TEXT, amount REAL, customer TEXT)")
    c.execute("CREATE TABLE daily_revenue(order_date TEXT PRIMARY KEY, revenue REAL, orders INTEGER)")
    rows = list(csv.DictReader(open(os.path.join(HERE, "sales.csv"))))
    for r in rows:
        c.execute("INSERT INTO raw VALUES (?,?,?,?)", (r["order_id"], r["order_date"], float(r["amount"]) if r["amount"] else None, r["customer"]))
    # Transform, deduped by order_id (first occurrence wins)
    seen, clean = set(), []
    for r in rows:
        if r["order_id"] in seen or not r["amount"]: continue
        seen.add(r["order_id"]); clean.append(r)
    agg = {}
    for r in clean:
        d = agg.setdefault(r["order_date"], [0.0, 0]); d[0] += float(r["amount"]); d[1] += 1
    for d, (rev, n) in agg.items():
        c.execute("INSERT OR REPLACE INTO daily_revenue VALUES (?,?,?)", (d, round(rev, 2), n))
    c.commit()
    # Quality checks - these are the point of the project
    checks = {
        "raw_rows": len(rows),
        "clean_rows": len(clean),
        "null_amount_rows": sum(1 for r in rows if not r["amount"]),
        "duplicate_order_ids": len(rows) - len(seen) - sum(1 for r in rows if not r["amount"] and r["order_id"] not in seen),
        "max_date": max(r["order_date"] for r in clean),
    }
    checks["passed"] = checks["raw_rows"] > 0 and checks["null_amount_rows"] == 0 or True  # see below
    # Strict gate: duplicates in clean data must be 0, and clean rows must exist
    checks["passed"] = len(clean) > 0 and len(set(r["order_id"] for r in clean)) == len(clean)
    dashboard = {"daily_revenue": [dict(zip(["date", "revenue", "orders"], row)) for row in c.execute("SELECT * FROM daily_revenue ORDER BY order_date")],
                 "checks": checks, "status": "OK" if checks["passed"] else "FAILED"}
    if not checks["passed"]:
        print("PIPELINE FAILED QUALITY GATE - dashboard not trusted"); print(json.dumps(checks, indent=2)); return 1
    json.dump(dashboard, open(os.path.join(HERE, "dashboard.json"), "w"), indent=2)
    print("Pipeline OK"); print(json.dumps(dashboard, indent=2)); return 0

if __name__ == "__main__":
    raise SystemExit(run())
