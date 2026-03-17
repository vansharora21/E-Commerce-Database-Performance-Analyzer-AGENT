import urllib.request, json

data = json.dumps({"question": "How much revenue did we generate this month?"}).encode()
req = urllib.request.Request(
    "http://localhost:8000/api/ask",
    data=data,
    headers={"Content-Type": "application/json", "X-Admin-Key": "VANSH2323"},
    method="POST"
)
try:
    with urllib.request.urlopen(req, timeout=90) as resp:
        result = json.loads(resp.read())
        print("SUCCESS!")
        print("HEADLINE:", result["insight"]["headline"])
        print("INTENT  :", result["intent"])
        print("TIME    :", result["execution_time_ms"], "ms")
        print("SUMMARY :", result["insight"]["summary"][:300])
        for m in result["insight"].get("key_metrics", []):
            print(f"  METRIC: {m.get('label')} = {m.get('value')} {m.get('unit')}")
        for r in result["insight"].get("recommendations", []):
            print(f"  REC: {r}")
except Exception as e:
    print("ERROR:", e)
