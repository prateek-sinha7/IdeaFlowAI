"""Generate static gallery thumbnails for OpenDesign templates (BUILD-TIME).

Screenshots each ``design-templates/<id>/example.html`` at 1280x720 and writes
``design-templates/<id>/thumbnail.jpg``. The catalog UI then serves that static
image (``GET /api/{prototype,ppt}/templates/<id>/thumbnail``, backed by
``od_loader.get_template_thumbnail_path``) instead of mounting a live ``<iframe>``
per card. Templates without a thumbnail fall back to live iframe rendering in the
browser, so this step is best-effort: it NEVER fails the build.

Where this runs
---------------
Baked into the backend image build (``backend/Dockerfile``): the runtime stage
already installs headless Chromium (``playwright install --with-deps chromium``
for ``render_check.py``) and bakes the OpenDesign tree at ``/app/opendesign``, so
generation reuses both. It also runs locally:

    cd backend && python scripts/generate_template_thumbnails.py

Flags:
    --dir <path>   design-templates directory (overrides OD_ROOT / default)
    --only <id>    generate a single template by folder name
    --force        re-generate even if thumbnail.jpg already exists

Exit code is always 0 (best-effort) so a flaky template can never break the
image build; failures are logged and the gallery degrades to live iframes.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import os
import socketserver
import sys
import threading
from pathlib import Path

VIEWPORT = {"width": 1280, "height": 720}
JPEG_QUALITY = 80
NAV_TIMEOUT_MS = 30_000
SETTLE_MS = 1_500
# Chromium flags required to run headless as root inside a Docker build
# (--no-sandbox) and with the small /dev/shm containers get.
LAUNCH_ARGS = ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]


def resolve_templates_dir(cli_dir: str | None) -> Path:
    if cli_dir:
        return Path(cli_dir).resolve()
    od_root = os.environ.get("OD_ROOT")
    if od_root:
        return Path(od_root) / "design-templates"
    # Default: repo-root/skills/opendesign/design-templates. This file lives at
    # backend/scripts/, so the repo root is two levels up.
    return Path(__file__).resolve().parents[2] / "skills" / "opendesign" / "design-templates"


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args):  # noqa: D401 — silence per-request logging
        pass


def start_static_server(root: Path) -> tuple[socketserver.TCPServer, int]:
    handler = functools.partial(_QuietHandler, directory=str(root))
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, port


def launch_browser(p):
    """Launch Chromium, preferring the bundled build and falling back to a
    system Chrome/Edge — lets the script run where the Playwright browser CDN
    is blocked but a Chromium-based browser is already present."""
    attempts = [
        ("bundled Chromium", {"args": LAUNCH_ARGS}),
        ("system Chrome", {"channel": "chrome", "args": LAUNCH_ARGS}),
        ("system Edge", {"channel": "msedge", "args": LAUNCH_ARGS}),
    ]
    for label, opts in attempts:
        try:
            browser = p.chromium.launch(**opts)
            print(f"Browser: {label}")
            return browser
        except Exception:  # noqa: BLE001 — try the next candidate
            continue
    return None


def list_template_ids(templates_dir: Path, only: str | None) -> list[str]:
    if only:
        return [only]
    return sorted(
        d.name
        for d in templates_dir.iterdir()
        if d.is_dir() and not d.name.startswith((".", "_"))
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate OpenDesign template thumbnails.")
    parser.add_argument("--dir", dest="dir", default=None)
    parser.add_argument("--only", dest="only", default=None)
    parser.add_argument("--force", dest="force", action="store_true")
    args = parser.parse_args()

    templates_dir = resolve_templates_dir(args.dir)
    if not templates_dir.is_dir():
        print(f"! design-templates directory not found: {templates_dir} — skipping thumbnails")
        return 0  # best-effort: never fail the build

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("! playwright not installed — skipping thumbnail generation")
        return 0

    print(f"OpenDesign templates dir: {templates_dir}")
    ids = list_template_ids(templates_dir, args.only)

    httpd, port = start_static_server(templates_dir)
    made = skipped = failed = 0

    try:
        with sync_playwright() as p:
            browser = launch_browser(p)
            if browser is None:
                print("! Could not launch a Chromium browser — skipping (gallery falls back to iframes)")
                return 0

            for tid in ids:
                example = templates_dir / tid / "example.html"
                out = templates_dir / tid / "thumbnail.jpg"
                if not example.is_file():
                    continue
                if not args.force and out.is_file():
                    skipped += 1
                    continue

                url = f"http://127.0.0.1:{port}/{tid}/example.html"
                context = None
                try:
                    context = browser.new_context(viewport=VIEWPORT, device_scale_factor=1)
                    page = context.new_page()
                    page.goto(url, wait_until="load", timeout=NAV_TIMEOUT_MS)
                    page.wait_for_timeout(SETTLE_MS)
                    page.screenshot(path=str(out), type="jpeg", quality=JPEG_QUALITY)
                    made += 1
                    print(f"  + {tid}")
                except Exception as exc:  # noqa: BLE001 — isolate per-template failures
                    failed += 1
                    print(f"  ! {tid} — {exc}")
                finally:
                    if context is not None:
                        try:
                            context.close()
                        except Exception:  # noqa: BLE001
                            pass

            try:
                browser.close()
            except Exception:  # noqa: BLE001
                pass
    finally:
        httpd.shutdown()

    print(f"\nDone. generated={made} skipped(existing)={skipped} failed={failed}")
    return 0  # always succeed — thumbnails are an optimization, not a hard dep


if __name__ == "__main__":
    sys.exit(main())
