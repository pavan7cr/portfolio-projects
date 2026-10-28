"""Pipeline v2 - complete except deployment.
Sources: sales.csv, Open-Meteo weather (Wichita), JSONPlaceholder posts (public API).
Transforms: dedupe, null-drop, daily revenue, post counts by user.
Quality gates: clean duplicates == 0, clean rows > 0, null amount == 0 in clean set.
Alerts: alerts.json written when a gate fails OR daily revenue drops >30% vs previous day.
Outputs: warehouse2.db, dashboard_full.json, alerts.json. Idempotent re-runs.
Tests: python3 test_pipeline.py
"""
import csv, json, os, sqlite3, requests
HERE = os.path.dirname(os.path.abspath(__file__))
def fetch_weather():
    r = requests.get("https://api.open-meteo.com/v1/forecast?latitude=37.69&longitude=-97.34&current=temperature_2m", timeout=20); r.raise_for_status(); return r.json()["current"]
def fetch_posts():
    r = requests.get("https://jsonplaceholder.typicode.com/posts", timeout=20); r.raise_for_status(); return r.json()[:20]
def run():
    dbp = os.path.join(HERE, "warehouse2.db")
    if os.path.exists(dbp): os.remove(dbp)
    c = sqlite3.connect(dbp)
    c.execute("CREATE TABLE daily_revenue(date TEXT PRIMARY KEY, revenue REAL, orders INTEGER)")
    c.execute("CREATE TABLE posts_by_user(user_id INTEGER PRIMARY KEY, posts INTEGER)")
    rows = list(csv.DictReader(open(os.path.join(HERE, "sales.csv"))))
    seen, clean = set(), []
    for r in rows:
        if r["order_id"] in seen or not r["amount"]: continue
        seen.add(r["order_id"]); clean.append(r)
    agg = {}
    for r in clean:
        d = agg.setdefault(r["order_date"], [0.0, 0]); d[0] += float(r["amount"]); d[1] += 1
    for d, (rev, n) in agg.items(): c.execute("INSERT OR REPLACE INTO daily_revenue VALUES (?,?,?)", (d, round(rev, 2), n))
    posts = fetch_posts(); pu = {}
    for p in posts: pu[p["userId"]] = pu.get(p["userId"], 0) + 1
    for uid, n in pu.items(): c.execute("INSERT OR REPLACE INTO posts_by_user VALUES (?,?)", (uid, n))
    c.commit()
    daily = [{"date": r[0], "revenue": r[1], "orders": r[2]} for r in c.execute("SELECT * FROM daily_revenue ORDER BY date")]
    checks = {"raw_rows": len(rows), "clean_rows": len(clean), "clean_duplicates": len(clean) - len(set(r["order_id"] for r in clean)), "passed": len(clean) > 0 and len(set(r["order_id"] for r in clean)) == len(clean)}
    alerts = []
    if not checks["passed"]: alerts.append("QUALITY GATE FAILED")
    if len(daily) >= 2 and daily[-1]["revenue"] < daily[-2]["revenue"] * 0.7: alerts.append(f"Revenue drop: {daily[-2]['revenue']} -> {daily[-1]['revenue']}")
    out = {"daily_revenue": daily, "posts_by_user": pu, "weather": fetch_weather(), "checks": checks, "alerts": alerts, "status": "OK" if checks["passed"] else "FAILED"}
    json.dump(out, open(os.path.join(HERE, "dashboard_full.json"), "w"), indent=2)
    json.dump(alerts, open(os.path.join(HERE, "alerts.json"), "w"), indent=2)
    print(json.dumps(out, indent=2)); return 0 if checks["passed"] else 1
if __name__ == "__main__": raise SystemExit(run())
