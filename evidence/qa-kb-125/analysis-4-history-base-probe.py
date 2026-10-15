"""
QA-KB-125 analysis probe #4 (read-only, no app server, no app code touched).

OD templates call history.replaceState(null, '', '#...') unguarded:
  html-ppt/assets/runtime.js:239, flowai-live-dashboard-template/assets/template.html:316,
  html-ppt/templates/layout-showcase.html:37, html-ppt/templates/single-page/code.html:23.
Probe #1 showed that call THROWS in every srcdoc document (D, and C even with allow-same-origin).
Does the <base href="about:srcdoc"> that fixes anchor navigation (probe #2, H) also fix the History API?
Also measures protocol-relative URL resolution under that base (the caveat for the fixer).
App origin simulated with page.route() on http://app.test/ -- no port is opened.
"""
import json
import sys
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

APP = "http://app.test"

DOC = """<!doctype html><html><head><meta charset="utf-8"><title>d</title>{HEAD}</head><body>
<img id="proto" src="//app.test/pixel.png"><img id="rel" src="pixel.png">
<script>
window.__ev = [];
addEventListener('hashchange', function(){ window.__ev.push('hashchange'); });
addEventListener('popstate', function(){ window.__ev.push('popstate'); });
(function () {
  var r = {};
  function t(k, f) { try { r[k] = f(); } catch (e) { r[k] = 'THREW ' + e.name; } }
  t('replaceState_#/3', function () { history.replaceState(null, '', '#/3'); return location.hash; });
  t('pushState_#/4', function () { history.pushState(null, '', '#/4'); return location.hash; });
  t('location.hash=#/5', function () { location.hash = '#/5'; return location.hash; });
  t('history.back()', function () { history.back(); return 'called'; });
  t('proto_relative_img.src', function () { return document.getElementById('proto').src; });
  t('relative_img.src', function () { return document.getElementById('rel').src; });
  t('document.baseURI', function () { return document.baseURI; });
  window.__r = r;
})();
</script></body></html>"""

PARENT = "<!doctype html><html><head><title>APP</title></head><body><div id='host'></div></body></html>"


def main() -> None:
    out = []

    def log(s: str = "") -> None:
        out.append(s)
        print(s)

    log(f"### QA-KB-125 history/base probe, {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        log(f"browser: Google Chrome {b.version} headless=True (channel=chrome, fresh temp profile)")
        ctx = b.new_context()
        page = ctx.new_page()
        page.route(APP + "/**", lambda r: r.fulfill(status=200, content_type="text/html", body=PARENT))
        page.goto(APP + "/runs/abc")

        def run(label: str, js: str, head: str = "") -> None:
            page.evaluate("document.getElementById('host').innerHTML=''")
            page.evaluate(
                """([js, html]) => { const f = document.createElement('iframe'); f.id='f';
                   new Function('f','html', js)(f, html); document.getElementById('host').appendChild(f); }""",
                [js, DOC.replace("{HEAD}", head)],
            )
            page.wait_for_timeout(900)
            fr = [x for x in page.frames if x != page.main_frame][0]
            res = fr.evaluate("window.__r")
            ev = fr.evaluate("window.__ev")
            log(f"[{label}]")
            for k, v in res.items():
                log(f"    {k}: {v}")
            log(f"    events fired: {ev}")
            log()

        run("D  srcdoc + sandbox='allow-scripts'",
            "f.setAttribute('sandbox','allow-scripts'); f.srcdoc = html;")
        run("H  srcdoc + sandbox='allow-scripts' + <base href=\"about:srcdoc\">",
            "f.setAttribute('sandbox','allow-scripts'); f.srcdoc = html;", '<base href="about:srcdoc">')
        run("A  blob: + sandbox='allow-scripts allow-same-origin'  (today's PrototypePreview, for comparison)",
            "f.setAttribute('sandbox','allow-scripts allow-same-origin');"
            "f.src = URL.createObjectURL(new Blob([html],{type:'text/html'}));")
        b.close()

    if len(sys.argv) > 1:
        with open(sys.argv[1], "w", encoding="utf-8") as fh:
            fh.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
