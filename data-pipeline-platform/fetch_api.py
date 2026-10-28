"""Second pipeline source: live public API (Open-Meteo, Wichita, KS).
Writes weather_current.json - a real external source, not a fixture.
Run after pipeline.py, or on a schedule: python3 fetch_api.py
"""
import json, os, requests
HERE = os.path.dirname(os.path.abspath(__file__))
r = requests.get("https://api.open-meteo.com/v1/forecast?latitude=37.69&longitude=-97.34&current=temperature_2m,wind_speed_10m", timeout=20)
r.raise_for_status()
data = {"source": "open-meteo", "location": "Wichita, KS", "current": r.json()["current"]}
json.dump(data, open(os.path.join(HERE, "weather_current.json"), "w"), indent=2)
print(json.dumps(data, indent=2))
