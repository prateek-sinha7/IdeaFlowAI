"""Read-only: size and type distribution of one run's /events payload (QA-KB-119 analysis).
Never prints the token or any payload content - only counts, sizes and event type names."""
import collections
import json
import sys
import urllib.request

BASE = "http://localhost:8000"
RUN = sys.argv[1] if len(sys.argv) > 1 else "78e185fb-c032-4154-8552-774781b6e5df"


def post_json(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


login = post_json("/api/auth/login", {"email": "admin@velocity.ai", "password": "Velocity!Dev2026"})
token = login.get("access_token") or login.get("token")
req = urllib.request.Request(f"{BASE}/api/runs/{RUN}/events", headers={"Authorization": f"Bearer {token}"})
with urllib.request.urlopen(req, timeout=120) as r:
    raw = r.read()
body = json.loads(raw)
ev = body["events"]
print(f"envelope keys: {sorted(body.keys())}")
print(f"row keys: {sorted(ev[0].keys())}")
print(f"events={len(ev)} bytes={len(raw)} avg_bytes_per_event={len(raw)/len(ev):.0f}")
seqs = [e["seq"] for e in ev]
print(f"seq: min={min(seqs)} max={max(seqs)} contiguous={seqs == list(range(seqs[0], seqs[0] + len(seqs)))}")

sizes = [(len(json.dumps(e["payload_json"], separators=(",", ":"))), e["type"]) for e in ev]
vals = sorted(s for s, _ in sizes)
q = lambda p: vals[min(len(vals) - 1, int(len(vals) * p))]
print(f"payload bytes: p50={q(.50)} p90={q(.90)} p99={q(.99)} p99.9={q(.999)} max={vals[-1]}")
for thr in (10_000, 50_000, 100_000, 200_000):
    print(f"  payloads > {thr:>7}: {sum(1 for s in vals if s > thr)}")

by_type = collections.defaultdict(lambda: [0, 0])
for s, t in sizes:
    by_type[t][0] += 1
    by_type[t][1] += s
tot = sum(v[1] for v in by_type.values())
print("top event types by payload bytes (type, count, bytes, share):")
for t, (c, b) in sorted(by_type.items(), key=lambda kv: -kv[1][1])[:10]:
    print(f"  {t:<28} {c:>7} {b:>11} {100*b/tot:5.1f}%")
chat = sum(v[0] for k, v in by_type.items() if k in ("chat_message", "chat_reply"))
chat_b = sum(v[1] for k, v in by_type.items() if k in ("chat_message", "chat_reply"))
print(f"chat_message+chat_reply: {chat} events, {chat_b} payload bytes ({100*chat_b/tot:.2f}% of payload bytes)")
# worst 40-row window by bytes (what a 40-row page could cost) and worst 1000-row window
import itertools
for w in (100, 1000):
    best = cur = sum(s for s, _ in sizes[:w])
    for i in range(w, len(sizes)):
        cur += sizes[i][0] - sizes[i - w][0]
        best = max(best, cur)
    print(f"worst contiguous {w:>4}-event window: {best} payload bytes")
