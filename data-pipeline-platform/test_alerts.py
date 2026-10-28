"""Alert-path tests. Run: venv/bin/python data-pipeline-platform/test_alerts.py
Uses a local mock HTTP server only; no real Slack/email secret is used.
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline_full import send_alerts  # noqa: E402

os.environ.pop("ALERT_WEBHOOK_URL", None)
captured = []


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        captured.append(json.loads(body))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


server = HTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{server.server_address[1]}/hook"

delivery = send_alerts(["QUALITY GATE FAILED"], webhook_url=url)
assert delivery["sent"] is True and delivery["via"] == "webhook", delivery
assert captured and captured[0]["alerts"] == ["QUALITY GATE FAILED"], captured

tmp = "/tmp/test_alerts_fallback.json"
if os.path.exists(tmp):
    os.remove(tmp)
delivery = send_alerts(["Revenue drop: 100 -> 50"], webhook_url=None, alerts_path=tmp)
assert delivery["via"] == "file", delivery
assert json.load(open(tmp)) == ["Revenue drop: 100 -> 50"]
server.shutdown()
print("alert tests passed")
