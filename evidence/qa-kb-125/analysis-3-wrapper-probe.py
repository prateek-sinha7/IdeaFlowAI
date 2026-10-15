"""
QA-KB-125 analysis probe #3 (read-only, no app server, no app code touched).

Validates the exact "Open in new tab" shape proposed for the fix:
  top-level blob: wrapper with NO script of its own
    -> <iframe sandbox="allow-scripts" srcdoc="<agent html with <base href=about:srcdoc>>">
and compares it with today's shape (agent HTML as the top-level blob document).
Also records window.opener exposure with and without the noopener window feature.
App origin simulated with page.route() on http://app.test/ -- no port is opened.
Real Google Chrome (channel="chrome"), fresh temporary profile.
"""
import json
import sys
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

APP = "http://app.test"

AGENT = """<!doctype html><html><head><meta charset="utf-8"><title>agent</title>{HEAD}</head><body>
<nav><a id="l1" href="#/p2">p2</a></nav>
<script>
window.__hc = 0;
addEventListener('hashchange', function(){ window.__hc++; });
(function () {
  var r = {};
  function t(k, f) { try { r[k] = f(); } catch (e) { r[k] = 'THREW ' + e.name; } }
  t('origin', function () { return String(self.origin); });
  t('app_localStorage_auth_token', function () { return localStorage.getItem('auth_token'); });
  t('top_document_title', function () { return String(top.document.title); });
  t('top_localStorage_auth_token', function () { return top.localStorage.getItem('auth_token'); });
  t('top_opener_is_object', function () { return typeof top.opener; });
  t('top_opener_localStorage', function () { return top.opener.localStorage.getItem('auth_token'); });
  t('own_opener_localStorage', function () { return opener.localStorage.getItem('auth_token'); });
  window.__r = r;
})();
</script></body></html>"""

PARENT = """<!doctype html><html><head><meta charset="utf-8"><title>APP-PARENT</title></head><body>
<h1>app</h1><div id="host"></div></body></html>"""


def esc_attr(s: str) -> str:
    return s.replace("&", "&amp;").replace('"', "&quot;")


def inject_base(html: str) -> str:
    # proposed helper behaviour: put <base href="about:srcdoc"> first in <head>
    return html.replace("{HEAD}", '<base href="about:srcdoc">')


def wrapper(html: str) -> str:
    return (
        '<!doctype html><meta charset="utf-8"><title>Preview</title>'
        "<style>html,body{margin:0;height:100%}iframe{border:0;width:100%;height:100%}</style>"
        f'<iframe sandbox="allow-scripts" srcdoc="{esc_attr(inject_base(html))}"></iframe>'
    )


def main() -> None:
    out = []

    def log(line: str = "") -> None:
        out.append(line)
        print(line)

    log(f"### QA-KB-125 wrapper probe, {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        log(f"browser: Google Chrome {browser.version} headless=True (channel=chrome, fresh temp profile)")
        ctx = browser.new_context()
        page = ctx.new_page()
        page.route(APP + "/**", lambda r: r.fulfill(status=200, content_type="text/html", body=PARENT))
        page.goto(APP + "/runs/abc")
        page.evaluate("localStorage.setItem('auth_token', 'SECRET-JWT-VALUE')")
        log("app localStorage.auth_token = SECRET-JWT-VALUE (canary), app origin http://app.test (route interception)")
        log()

        def run(label: str, doc_js: str, features: str) -> None:
            page.evaluate("document.getElementById('host').innerHTML = ''")
            page.evaluate(
                """([docJs, agent, wrapperHtml, features]) => {
                    const btn = document.createElement('button');
                    btn.id = 'open';
                    btn.onclick = () => {
                      const mk = new Function('agent', 'wrapperHtml', docJs);
                      const url = URL.createObjectURL(new Blob([mk(agent, wrapperHtml)], {type:'text/html'}));
                      window.open(url, '_blank', features || undefined);
                    };
                    document.getElementById('host').appendChild(btn);
                }""",
                [doc_js, AGENT.replace("{HEAD}", ""), wrapper(AGENT), features],
            )
            popup = None
            try:
                with ctx.expect_page(timeout=4000) as pop:
                    page.click("#open")
                popup = pop.value
            except Exception as e:  # noqa: BLE001
                log(f"[{label}] popup did not open: {str(e).splitlines()[0][:80]}")
                return
            popup.wait_for_load_state("load")
            popup.wait_for_timeout(700)
            log(f"[{label}]  window.open features: {features!r}")
            log(f"    top-level origin: {popup.evaluate('self.origin')}")
            log(f"    top-level window.opener is {'present' if popup.evaluate('!!window.opener') else 'null'}")
            kids = [fr for fr in popup.frames if fr != popup.main_frame]
            agent_frame = kids[0] if kids else popup.main_frame
            res = agent_frame.evaluate("window.__r")
            log(f"    agent HTML runs in: {'nested sandboxed srcdoc frame' if kids else 'the top-level document'}")
            for k, v in res.items():
                log(f"        sees {k}: {v}")
            # navigation inside the agent frame
            try:
                agent_frame.click("#l1", timeout=2500)
                popup.wait_for_timeout(300)
                agent_frame = [fr for fr in popup.frames if fr != popup.main_frame][0] if kids else popup.main_frame
                st = agent_frame.evaluate("({hash: location.hash, href: location.href.slice(0,40), hc: window.__hc})")
            except Exception as e:  # noqa: BLE001
                st = f"click/eval failed: {str(e).splitlines()[0][:80]}"
            log(f"        after clicking <a href=\"#/p2\">: {st}")
            popup.close()
            log()

        run("E  today: agent HTML IS the top-level blob document", "return agent;", "")
        run("G1 proposed: script-free wrapper + nested sandbox=allow-scripts srcdoc + <base href=about:srcdoc>", "return wrapperHtml;", "")
        run("G2 proposed + noopener", "return wrapperHtml;", "noopener,noreferrer")
        browser.close()

    if len(sys.argv) > 1:
        with open(sys.argv[1], "w", encoding="utf-8") as fh:
            fh.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
