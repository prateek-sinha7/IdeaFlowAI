"""
QA-KB-125 analysis probe (read-only, no app server, no app code touched).

Question 1: what origin does agent HTML get in each in-app configuration, and can it
            read the app's localStorage / reach the parent?
Question 2: if allow-same-origin is dropped, do the things the generated HTML actually
            does (location.hash routing, history.replaceState('#..'), hashchange) still work?
Question 3: which "Open in new tab" shape gives the agent HTML an opaque origin?

The app origin is simulated with page.route() on http://app.test/ -- nothing listens on a port.
Real Google Chrome (channel="chrome"), fresh temporary profile.
"""
import json
import sys
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

APP = "http://app.test"
SECRET = "SECRET-JWT-VALUE"

# What the agent HTML does at runtime. Mirrors what the repo's OD templates do:
#   html-ppt/assets/runtime.js:239   history.replaceState(null,'', '#/n')  (unguarded)
#   flowai-live-dashboard-template   history.replaceState(null, "", "#" + v)  (unguarded)
#   hash routing                      location.hash = '#/x' + hashchange
#   storage                           localStorage.getItem(...)
CHILD = """<!doctype html><html><head><meta charset="utf-8"><title>child</title></head><body>
<script>
(function () {
  var r = {};
  function t(k, f) { try { r[k] = f(); } catch (e) { r[k] = 'THREW ' + e.name; } }
  t('origin', function () { return String(self.origin); });
  t('app_localStorage_auth_token', function () { return localStorage.getItem('auth_token'); });
  t('document_cookie_typeof', function () { return typeof document.cookie; });
  t('parent_document_title', function () { return String(parent.document.title); });
  t('parent_localStorage_auth_token', function () { return parent.localStorage.getItem('auth_token'); });
  t('top_localStorage_auth_token', function () { return top.localStorage.getItem('auth_token'); });
  t('location_hash_assign', function () { location.hash = '#/2'; return location.hash; });
  t('history_replaceState_hash', function () { history.replaceState(null, '', '#/3'); return location.hash; });
  var hc = 0;
  addEventListener('hashchange', function () { hc++; document.title = document.title.replace(/"hashchange_events":\\d+/, '"hashchange_events":' + hc); });
  t('location_hash_assign_2', function () { location.hash = '#/4'; return location.hash; });
  r.hashchange_events = 0;
  document.title = JSON.stringify(r);
})();
</script></body></html>"""

PARENT = """<!doctype html><html><head><meta charset="utf-8"><title>APP-PARENT</title></head><body>
<h1>app</h1>
<div id="host"></div>
</body></html>"""


def esc_attr(s: str) -> str:
    return s.replace("&", "&amp;").replace('"', "&quot;")


def wrapper_html(child_html: str) -> str:
    # Candidate "Open in new tab" shape: a script-free wrapper whose only content is a
    # sandboxed srcdoc frame holding the agent HTML.
    return (
        '<!doctype html><meta charset="utf-8"><title>Preview</title>'
        "<style>html,body{margin:0;height:100%}iframe{border:0;width:100%;height:100%}</style>"
        f'<iframe sandbox="allow-scripts" srcdoc="{esc_attr(child_html)}"></iframe>'
    )


META_CSP_DOC = CHILD.replace(
    "<head>",
    '<head><meta http-equiv="Content-Security-Policy" content="sandbox allow-scripts">',
)


def main() -> None:
    out = []

    def log(line: str = "") -> None:
        out.append(line)
        print(line)

    log(f"### QA-KB-125 analysis probe, {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        log(f"browser: Google Chrome {browser.version} headless=True  (channel=chrome, fresh temp profile)")
        ctx = browser.new_context()
        page = ctx.new_page()

        def fulfill(route):
            route.fulfill(status=200, content_type="text/html", body=PARENT)

        page.route(APP + "/**", fulfill)
        page.goto(APP + "/")
        page.evaluate(f"localStorage.setItem('auth_token', '{SECRET}')")
        log(f"app origin simulated: {page.evaluate('location.origin')}  (page.route interception, no server)")
        log(f"app localStorage.auth_token set to a canary: {SECRET}")
        log()

        # ---- in-app iframes -------------------------------------------------
        variants = [
            ("A  blob: src  + sandbox='allow-scripts allow-same-origin'   (PrototypePreview.tsx:610, today)", "blob", "allow-scripts allow-same-origin"),
            ("B  blob: src  + sandbox='allow-scripts'                      (candidate)", "blob", "allow-scripts"),
            ("C  srcdoc     + sandbox='allow-scripts allow-same-origin'   (PPTPreview.tsx:252, today)", "srcdoc", "allow-scripts allow-same-origin"),
            ("D  srcdoc     + sandbox='allow-scripts'                      (generic renderer PreviewPanel.tsx:278 / candidate)", "srcdoc", "allow-scripts"),
        ]
        for label, kind, sandbox in variants:
            page.evaluate(
                """([kind, sandbox, child]) => {
                    const host = document.getElementById('host');
                    host.innerHTML = '';
                    const f = document.createElement('iframe');
                    f.setAttribute('sandbox', sandbox);
                    f.id = 'f';
                    if (kind === 'blob') {
                      f.src = URL.createObjectURL(new Blob([child], { type: 'text/html' }));
                    } else {
                      f.srcdoc = child;
                    }
                    host.appendChild(f);
                }""",
                [kind, sandbox, CHILD],
            )
            page.wait_for_function(
                "() => { const f = document.getElementById('f'); return f && f.contentWindow && true; }"
            )
            page.wait_for_timeout(600)
            frame = [fr for fr in page.frames if fr != page.main_frame][0]
            title = frame.evaluate("document.title")
            res = json.loads(title) if title.startswith("{") else {"title": title}
            # what the PARENT can do to the iframe (this is the parent-side coupling check)
            try:
                parent_reads = page.evaluate(
                    "() => { try { return document.getElementById('f').contentWindow.localStorage.getItem('auth_token'); } catch (e) { return 'THREW ' + e.name; } }"
                )
            except Exception as e:  # noqa: BLE001
                parent_reads = f"ERR {e}"
            log(f"[{label}]")
            for k, v in res.items():
                log(f"    child sees  {k}: {v}")
            log(f"    parent can read iframe.contentWindow.localStorage.auth_token: {parent_reads}")
            log()

        # ---- Open in new tab shapes ----------------------------------------
        def open_tab(label: str, make_url_js: str) -> None:
            page.evaluate("document.getElementById('host').innerHTML = ''")
            page.evaluate(
                """([js, child, wrapperHtml, metaDoc]) => {
                    const btn = document.createElement('button');
                    btn.id = 'open';
                    btn.textContent = 'open';
                    btn.onclick = () => {
                      const mk = new Function('child', 'wrapperHtml', 'metaDoc', js);
                      const url = mk(child, wrapperHtml, metaDoc);
                      window.open(url, '_blank');
                    };
                    document.getElementById('host').appendChild(btn);
                }""",
                [make_url_js, CHILD, wrapper_html(CHILD), META_CSP_DOC],
            )
            with ctx.expect_page() as pop:
                page.click("#open")
            popup = pop.value
            popup.wait_for_load_state("load")
            popup.wait_for_timeout(700)
            top_url = popup.url
            top_origin = popup.evaluate("self.origin")
            try:
                top_ls = popup.evaluate("localStorage.getItem('auth_token')")
            except Exception as e:  # noqa: BLE001
                top_ls = f"THREW ({str(e).splitlines()[0][:70]})"
            log(f"[{label}]")
            log(f"    new tab top-level URL: {top_url[:60]}...")
            log(f"    new tab top-level document origin: {top_origin}")
            log(f"    new tab top-level localStorage.auth_token readable: {top_ls}")
            kids = [fr for fr in popup.frames if fr != popup.main_frame]
            if kids:
                title = kids[0].evaluate("document.title")
                res = json.loads(title) if title.startswith("{") else {"title": title}
                log("    agent HTML runs in a NESTED frame; child sees:")
                for k, v in res.items():
                    log(f"        {k}: {v}")
            else:
                title = popup.evaluate("document.title")
                res = json.loads(title) if title.startswith("{") else {"title": title}
                log("    agent HTML runs AS the top-level document; it sees:")
                for k, v in res.items():
                    log(f"        {k}: {v}")
            popup.close()
            log()

        open_tab(
            "E  window.open(blobUrl)  -- today: PrototypePreview.tsx:389, PreviewPanel.tsx:1597, :2182, WorkflowHistory.tsx:1006, PPTPreview.tsx:211",
            "return URL.createObjectURL(new Blob([child], {type:'text/html'}));",
        )
        open_tab(
            "F  window.open(blobUrl of a doc with <meta CSP sandbox allow-scripts>)  -- the tempting one-line fix",
            "return URL.createObjectURL(new Blob([metaDoc], {type:'text/html'}));",
        )
        open_tab(
            "G  window.open(blobUrl of a script-free WRAPPER holding <iframe sandbox='allow-scripts' srcdoc=...>)  -- candidate",
            "return URL.createObjectURL(new Blob([wrapperHtml], {type:'text/html'}));",
        )
        browser.close()

    return_text = "\n".join(out)
    if len(sys.argv) > 1:
        with open(sys.argv[1], "w", encoding="utf-8") as fh:
            fh.write(return_text + "\n")


if __name__ == "__main__":
    main()
