import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
r = subprocess.run([sys.executable, os.path.join(HERE, "pipeline_full.py")], capture_output=True, text=True)
assert r.returncode == 0, r.stdout + r.stderr
d = json.load(open(os.path.join(HERE, "dashboard_full.json")))
assert d["checks"]["passed"] and d["daily_revenue"][0]["revenue"] == 200.5, d
assert sum(d["posts_by_user"].values()) == 20
# idempotency: second run gives same daily revenue, not doubled
subprocess.run([sys.executable, os.path.join(HERE, "pipeline_full.py")], capture_output=True)
d2 = json.load(open(os.path.join(HERE, "dashboard_full.json")))
assert d2["daily_revenue"] == d["daily_revenue"], "re-run changed revenue - not idempotent"
print("pipeline tests passed")
