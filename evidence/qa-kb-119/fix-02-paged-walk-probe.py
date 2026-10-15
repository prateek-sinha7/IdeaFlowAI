"""Read-only probe for QA-KB-119 after the fix: walk GET /api/runs/{id}/events page by page,
the way frontend getRunEvents does (after=<next_after>, limit=5000, until has_more is false),
and probe GET /health on another thread for the whole walk.

Checks the paged walk returns the WHOLE log: seq 1..N, contiguous, no duplicate.
Never prints the token. Writes only to stdout.
"""
import json
import sys
import threading
import time
import urllib.request

BASE = "http://localhost:8000"
RUN = sys.argv[1] if len(sys.argv) > 1 else "78e185fb-c032-4154-8552-774781b6e5df"
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 5000


def post_json(path, body):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def health():
    t0 = time.monotonic()
    with urllib.request.urlopen(BASE + "/health", timeout=60) as r:
        r.read()
    return time.monotonic() - t0


login = post_json("/api/auth/login", {"email": "admin@velocity.ai", "password": "Velocity!Dev2026"})
token = login.get("access_token") or login.get("token")
assert token, f"no token key in login response; keys={list(login)}"

done = threading.Event()
lat = []


def prober():
    while not done.is_set():
        lat.append(health())
        time.sleep(0.05)


th = threading.Thread(target=prober)
th.start()
seqs, pages, total_bytes, worst_page_s, worst_page_bytes, after = [], 0, 0, 0.0, 0, 0
T0 = time.monotonic()
while True:
    t0 = time.monotonic()
    req = urllib.request.Request(
        f"{BASE}/api/runs/{RUN}/events?after={after}&limit={LIMIT}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    dt = time.monotonic() - t0
    body = json.loads(raw)
    pages += 1
    total_bytes += len(raw)
    worst_page_s = max(worst_page_s, dt)
    worst_page_bytes = max(worst_page_bytes, len(raw))
    seqs += [e["seq"] for e in body["events"]]
    if not body.get("has_more"):
        break
    assert body["next_after"] > after, "cursor did not advance"
    after = body["next_after"]
walk_s = time.monotonic() - T0
done.set()
th.join()

print(f"walk: limit={LIMIT} pages={pages} events={len(seqs)} bytes={total_bytes} total={walk_s:.2f}s")
print(f"worst page: {worst_page_s:.2f}s, largest page: {worst_page_bytes} bytes")
print(f"seq contiguous 1..N, no duplicate: {seqs == list(range(1, len(seqs) + 1))}")
print(f"/health during the walk: n={len(lat)} worst={max(lat)*1000:.0f}ms "
      f"p50={sorted(lat)[len(lat)//2]*1000:.0f}ms over 300ms={sum(1 for x in lat if x > 0.3)}")
