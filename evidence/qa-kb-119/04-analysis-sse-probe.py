"""Read-only probe for QA-KB-119: does one bare GET /api/runs/{id}/events stall the event loop?

Measures GET /health latency (async def, no I/O) BEFORE and DURING one bare /events call.
Never prints the token. Writes only to stdout.
"""
import json
import sys
import threading
import time
import urllib.request

BASE = "http://localhost:8000"
RUN = sys.argv[1] if len(sys.argv) > 1 else "78e185fb-c032-4154-8552-774781b6e5df"
QUERY = sys.argv[2] if len(sys.argv) > 2 else ""  # e.g. "?after=0"


def post_json(path, body):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def health():
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(BASE + "/health", timeout=60) as r:
            r.read()
            code = r.status
    except Exception as exc:  # noqa: BLE001
        code = f"ERR {type(exc).__name__}"
    return time.monotonic() - t0, code


login = post_json("/api/auth/login", {"email": "admin@velocity.ai", "password": "Velocity!Dev2026"})
token = login.get("access_token") or login.get("token")
assert token, f"no token key in login response; keys={list(login)}"

# ---- baseline: 8 sequential /health calls, idle -------------------------------------------
base = [health()[0] for _ in range(8)]
print(f"baseline /health (idle, n=8): max={max(base)*1000:.0f}ms median={sorted(base)[4]*1000:.0f}ms")

# ---- the big call, in a thread; probe /health on the main thread while it runs -----------
big = {}


def big_call():
    t0 = time.monotonic()
    req = urllib.request.Request(
        f"{BASE}/api/runs/{RUN}/events/stream{QUERY}", headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        big["status"] = r.status
        big["ttfb_s"] = time.monotonic() - t0  # headers received
        n = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            n += len(chunk)
        big["bytes"] = n
    big["total_s"] = time.monotonic() - t0


th = threading.Thread(target=big_call)
T0 = time.monotonic()
th.start()
time.sleep(0.15)  # let the request reach the server
probes = []  # (start_offset_s, latency_s, code)
while th.is_alive():
    s = time.monotonic() - T0
    lat, code = health()
    probes.append((s, lat, code))
    time.sleep(0.05)
th.join()

print(f"big call: status={big.get('status')} bytes={big.get('bytes')} "
      f"ttfb={big.get('ttfb_s', 0):.2f}s total={big.get('total_s', 0):.2f}s")
print(f"/health probes during the big call: n={len(probes)}")
for s, lat, code in probes:
    print(f"  t+{s:5.2f}s  latency={lat*1000:7.0f}ms  {code}")
worst = max((p[1] for p in probes), default=0)
print(f"WORST /health latency while /events in flight: {worst*1000:.0f}ms "
      f"(idle baseline max {max(base)*1000:.0f}ms)")
