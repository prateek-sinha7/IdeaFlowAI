#!/usr/bin/env python3
"""QA-KB-053 sibling proof (READ-ONLY, GET only): the path the LIVE tree resolves vs. the same path read AT the member's ref.

PreviewPanel.tsx:1437 resolves deliverableFile with resolveRunDeliverable(token, activeRunId, declared) -- no ref -- and
PreviewPanel.tsx:1485-1487 (FIX-603) then reads that path AT sandboxSelectedRef. When the live tree and the tag disagree
about WHERE the file is, the read at the ref is a 404.

Usage: VELOCITY_EMAIL=... VELOCITY_PASSWORD=... python3 path-at-ref-probe.py <member_id> <tag> <path>
"""
import json, os, sys, urllib.error, urllib.parse, urllib.request

BASE = os.environ.get("VELOCITY_API", "http://localhost:8000")

def call(method, path, token=None, body=None):
    req = urllib.request.Request(BASE + path, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, data=json.dumps(body).encode() if body is not None else None, timeout=60) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()

st, out = call("POST", "/api/auth/login", body={"email": os.environ["VELOCITY_EMAIL"], "password": os.environ["VELOCITY_PASSWORD"]})
tok = json.loads(out.decode())["token"]
member, tag, path = sys.argv[1:4]
q = urllib.parse.quote(path)
s_live, b_live = call("GET", f"/api/runs/{member}/sandbox/file?path={q}", tok)
s_ref, b_ref = call("GET", f"/api/runs/{member}/sandbox/file?path={q}&ref={urllib.parse.quote(tag)}", tok)
print(f"GET /api/runs/{member}/sandbox/file?path={path}              -> HTTP {s_live}  ({len(b_live)} bytes)")
print(f"GET /api/runs/{member}/sandbox/file?path={path}&ref={tag}    -> HTTP {s_ref}  {b_ref[:80]!r}" if s_ref != 200 else
      f"GET /api/runs/{member}/sandbox/file?path={path}&ref={tag}    -> HTTP {s_ref}  ({len(b_ref)} bytes)")
