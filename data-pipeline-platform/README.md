# Data Pipeline Platform MVP - what was built
- Ingests sales.csv, dedupes by order_id, drops missing-amount rows, aggregates daily revenue into SQLite.
- Quality gate: clean data must have no duplicate order_ids and at least one row, otherwise run is FAILED and dashboard is not trusted.
- Output: warehouse.db + dashboard.json. Re-runs replace daily rows (idempotent), not duplicate them.
- Run: python3 pipeline.py
## Round 2 (2026-10-28)
- Added fetch_api.py: live Open-Meteo Wichita weather source, tested 2026-10-28 (22.8C, wind 22.5 km/h at 17:15 UTC).
- Added dashboard.html and run_daily.sh (cron-ready daily run).
- Still to do: React dashboard, alerting, more sources, deployment.
