# Scheduled / Batch Data Pipeline Platform - what was built (renamed 2026-10-28: ingestion is scheduled/batch, not streaming)
- Ingests sales.csv, dedupes by order_id, drops missing-amount rows, aggregates daily revenue into SQLite.
- Quality gate: clean data must have no duplicate order_ids and at least one row, otherwise run is FAILED and dashboard is not trusted.
- Output: warehouse.db + dashboard.json. Re-runs replace daily rows (idempotent), not duplicate them.
- Run: python3 pipeline.py
## Round 2 (2026-10-28)
- Added fetch_api.py: live Open-Meteo Wichita weather source, tested 2026-10-28 (22.8C, wind 22.5 km/h at 17:15 UTC).
- Added dashboard.html and run_daily.sh (cron-ready daily run).
- Still to do: React dashboard, alerting, more sources, deployment.
## 2026-10-28 upgrades
- Synthetic generator (generate_sales.py): 50,000 rows in -> 46,000 clean out, 2,500 duplicates removed, 1,500 null rows removed, 30 days of daily revenue, total synthetic revenue $11,696,354.36, runtime 0.385s on a local run, re-run total unchanged (idempotent).
- Alerts: ALERT_WEBHOOK_URL posts alerts to a webhook; without one, alerts.json is the fallback. Tested with a local mock endpoint in test_alerts.py, not a real secret.
- Dashboard: dashboard.html now shows daily revenue bars plus quality-gate run history (run_history.jsonl).
- Scheduled run: .github/workflows/pipeline-daily.yml runs the synthetic pipeline daily on GitHub Actions (free). No Render Cron Job was created (paid, no free plan).
