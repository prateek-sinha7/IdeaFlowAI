"""
QA-KB-125 analysis probe #2 (read-only, no app server, no app code touched).

Why PrototypePreview.tsx:610 carries allow-same-origin: commit 77228e567 (2026-05-20) says it "enables the
SPA hash router in the generated prototype HTML". Probe #1 showed that in a blob: iframe WITHOUT
allow-same-origin, `location.hash = ...` is a silent no-op. This probe measures the navigation shapes a generated
SPA actually uses -- `<a href="#/p2">` clicks, `location.hash =`, hashchange -- under every candidate replacement,
so the fixer knows which one keeps prototypes navigable.

App origin is simulated with page.route() on http://app.test/ (nothing listens on a port).
Real Google Chrome (channel="chrome"), fresh temporary profile.
"""
import json
import sys
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

APP = "http://app.test"

# A minimal generated-SPA: anchor nav + hashchange router + a storage read that is NOT try/caught.
SPA = """<!doctype html><html><head><meta charset="utf-8"><title>spa</title>{HEAD}</head><body>
<nav><a id="l1" href="#/p2">p2</a> <a id="l2" href="#p3">p3</a></nav>
<script>
window.__hc = 0;
window.addEventListener('hashchange', function(){ window.__hc++; });
</script></body></html>"""

PARENT = """<!doctype html><html><head><meta charset="utf-8"><title>APP-PARENT</title></head><body>
<h1>app</h1><div id="host"></div></body></html>"""

SHARE = SPA.replace("{HEAD}", "")  # served with a real CSP header via route fulfil below


def main() -> None:
    out = []

    def log(line: str = "") -> None:
        out.append(line)
        print(line)

    log(f"### QA-KB-125 navigation probe, {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        log(f"browser: Google Chrome {browser.version} headless=True (channel=chrome, fresh temp profile)")
        ctx = browser.new_context()
        page = ctx.new_page()

        def route(r):
            url = r.request.url
            if url.startswith(APP + "/shared"):
                r.fulfill(status=200, content_type="text/html", body=SHARE,
                          headers={"Content-Security-Policy": "sandbox allow-scripts"})
            else:
                r.fulfill(status=200, content_type="text/html", body=PARENT)

        page.route(APP + "/**", route)
        page.goto(APP + "/runs/abc")
        log(f"parent page URL: {page.url}")
        log()

        def probe(label: str, make_js: str, head: str = "") -> None:
            html = SPA.replace("{HEAD}", head)
            page.evaluate("document.getElementById('host').innerHTML = ''")
            page.evaluate(
                """([js, html]) => {
                    const host = document.getElementById('host');
                    const f = document.createElement('iframe');
                    f.id = 'f';
                    f.style.cssText = 'width:600px;height:300px';
                    const mk = new Function('f', 'html', js);
                    mk(f, html);
                    host.appendChild(f);
                }""",
                [make_js, html],
            )
            page.wait_for_timeout(700)
            frame = [fr for fr in page.frames if fr != page.main_frame][0]
            res = {}
            res["frame_url_before"] = frame.url[:48]

            def snap(tag):
                try:
                    res[tag] = frame.evaluate(
                        "() => ({hash: location.hash, href: location.href.slice(0,60), hc: window.__hc})"
                    )
                except Exception as e:  # noqa: BLE001
                    res[tag] = f"ERR {str(e).splitlines()[0][:80]}"

            snap("initial")
            # 1) anchor click  <a href="#/p2">
            try:
                frame.click("#l1", timeout=2500)
                page.wait_for_timeout(400)
            except Exception as e:  # noqa: BLE001
                res["click_l1_error"] = str(e).splitlines()[0][:80]
            frame = [fr for fr in page.frames if fr != page.main_frame][0]
            res["frame_url_after_l1"] = frame.url[:70]
            snap("after_click_l1_#/p2")
            # 2) anchor click  <a href="#p3">
            try:
                frame.click("#l2", timeout=2500)
                page.wait_for_timeout(400)
            except Exception as e:  # noqa: BLE001
                res["click_l2_error"] = str(e).splitlines()[0][:80]
            frame = [fr for fr in page.frames if fr != page.main_frame][0]
            res["frame_url_after_l2"] = frame.url[:70]
            snap("after_click_l2_#p3")
            # 3) location.hash =
            try:
                frame.evaluate("location.hash = '#/p4'")
                page.wait_for_timeout(300)
            except Exception as e:  # noqa: BLE001
                res["assign_error"] = str(e).splitlines()[0][:80]
            frame = [fr for fr in page.frames if fr != page.main_frame][0]
            snap("after_assign_#/p4")
            log(f"[{label}]")
            for k, v in res.items():
                log(f"    {k}: {v}")
            log()

        probe("A  blob: src + sandbox='allow-scripts allow-same-origin'  (PrototypePreview today)",
              "f.setAttribute('sandbox','allow-scripts allow-same-origin');"
              "f.src = URL.createObjectURL(new Blob([html],{type:'text/html'}));")
        probe("B  blob: src + sandbox='allow-scripts'",
              "f.setAttribute('sandbox','allow-scripts');"
              "f.src = URL.createObjectURL(new Blob([html],{type:'text/html'}));")
        probe("C  srcdoc + sandbox='allow-scripts allow-same-origin'  (PPTPreview today)",
              "f.setAttribute('sandbox','allow-scripts allow-same-origin'); f.srcdoc = html;")
        probe("D  srcdoc + sandbox='allow-scripts'  (generic renderer today)",
              "f.setAttribute('sandbox','allow-scripts'); f.srcdoc = html;")
        probe("H  srcdoc + sandbox='allow-scripts' + <base href=\"about:srcdoc\"> injected into <head>",
              "f.setAttribute('sandbox','allow-scripts'); f.srcdoc = html;",
              head='<base href="about:srcdoc">')
        probe("I  http iframe src=/shared served with response header 'Content-Security-Policy: sandbox allow-scripts'  (the FIX-745 share-link shape)",
              "f.src = 'http://app.test/shared';")
        browser.close()

    if len(sys.argv) > 1:
        with open(sys.argv[1], "w", encoding="utf-8") as fh:
            fh.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
