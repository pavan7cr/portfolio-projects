#!/bin/bash
# Schedule-ready daily run: cd to this folder, then
# crontab: 0 6 * * * /path/to/data-pipeline-platform/run_daily.sh
cd "$(dirname "$0")"
python3 pipeline.py && python3 fetch_api.py
