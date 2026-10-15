#!/usr/bin/env python3
"""QA-KB-053 analysis proof — READ-ONLY (GET only, plus the login POST).

For each member of a revision family, mirror what FilesTab does for its deliverable row:

    resolveRunDeliverable(token, memberId)            -> GET /api/runs/{member}/sandbox            (NO ref, today)
    the fix                                           -> GET /api/runs/{member}/sandbox?ref=<tag>  (the member's own snapshot)
    Download of the resolved row                      -> GET .../sandbox/file?path=<p>[&ref=<tag>]

and print name/size/sha256 of each, using resolveRunDeliverable's candidate order
(frontend/src/lib/api.ts:1606-1637: declared .html -> <stem>.pptx first; then the declared file; then .chain/<candidate>).

Usage:  VELOCITY_EMAIL=... VELOCITY_PASSWORD=... python3 family-probe.py <family_root_id> [<family_root_id> ...]
Prints no token. Nothing is created, changed or deleted.
"""
import hashlib, json, os, sys, urllib.error, urllib.parse, urllib.request

BASE = os.environ.get("VELOCITY_API", "http://localhost:8000")


def _open(req, data=None):
    try:
        with urllib.request.urlopen(req, data=data, timeout=60) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def raw(path, token):
    req = urllib.request.Request(BASE + path, method="GET")
    req.add_header("Authorization", "Bearer " + token)
    return _open(req)


def js(path, token):
    st, body = raw(path, token)
    try:
        return st, json.loads(body.decode() or "null")
    except Exception:
        return st, None


def login():
    req = urllib.request.Request(BASE + "/api/auth/login", method="POST")
    req.add_header("Content-Type", "application/json")
    body = json.dumps({"email": os.environ["VELOCITY_EMAIL"], "password": os.environ["VELOCITY_PASSWORD"]}).encode()
    st, out = _open(req, body)
    return json.loads(out.decode())["token"]


def candidates(name):
    dot = name.rfind(".")
    stem, ext = (name[:dot], name[dot + 1:].lower()) if dot > 0 else (name, "")
    c = [f"{stem}.pptx", name] if ext == "html" else ([name, f"{stem}.html"] if ext == "pptx" else [name])
    return list(dict.fromkeys(c))


def resolve(listing, name):
    files = {f["path"]: f for f in listing.get("files", [])}
    c = candidates(name)
    for p in c:
        if p in files:
            return files[p]
    for p in c:
        if f".chain/{p}" in files:
            return files[f".chain/{p}"]
    return None


def main():
    tok = login()
    for root in sys.argv[1:]:
        st, fam = js(f"/api/runs/{root}/family", tok)
        print(f"=== family root {root}")
        for m in fam["members"]:
            mid, tag = m["id"], m.get("git_tag")
            st, run = js(f"/api/runs/{mid}", tok)
            declared = (run or {}).get("deliverableFilename") or (run or {}).get("deliverable_filename")
            print(f"  v{m['revision_index']} {mid} {m['type']:<28} {m['status']:<10} tag={tag} declared={declared}")
            if not declared:
                print("      (no declared deliverable -> FilesTab keeps the derived row; nothing to reconcile)")
                continue
            st, live = js(f"/api/runs/{mid}/sandbox", tok)
            hit = resolve(live, declared) if live else None
            def fmt(h):
                return "none" if not h else f"{h['path']} ({h['size']} B)"
            print(f"      NO ref  (FilesTab today)   : {fmt(hit)}")
            h_live = "-"
            if hit:
                s1, b1 = raw(f"/api/runs/{mid}/sandbox/file?path={urllib.parse.quote(hit['path'])}", tok)
                h_live = hashlib.sha256(b1).hexdigest()[:12] if s1 == 200 else f"HTTP{s1}"
            rhit, h_ref = None, "-"
            if tag:
                st, rl = js(f"/api/runs/{mid}/sandbox?ref={urllib.parse.quote(tag)}", tok)
                rhit = resolve(rl, declared) if rl else None
                if rhit:
                    s2, b2 = raw(f"/api/runs/{mid}/sandbox/file?path={urllib.parse.quote(rhit['path'])}&ref={urllib.parse.quote(tag)}", tok)
                    h_ref = hashlib.sha256(b2).hexdigest()[:12] if s2 == 200 else f"HTTP{s2}"
                print(f"      ref={tag:<4} (member's own)  : {fmt(rhit)}")
            else:
                print("      ref=None (member has no git tag -> nothing to scope to)")
            print(f"      bytes sha256[:12]: no-ref={h_live} ref={h_ref}" + ("   <-- DIFFERENT" if "-" not in (h_live, h_ref) and h_live != h_ref else ""))


if __name__ == "__main__":
    main()
