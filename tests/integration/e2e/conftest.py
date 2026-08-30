"""Fixtures for the integration suite.

`pytest-playwright` already supplies `page`, `browser`, `--headed`,
`--browser-channel` and `--base-url`, so none of that is rebuilt here. This file
adds only the two things it does not have: a run folder, and the screenshot
writer bound to it.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path


import pytest

from framework import accounts, settings
from framework import run_report
from framework.report import Reporter
from framework.shot import Shooter, slugify

INTEGRATION = Path(__file__).resolve().parent.parent


def pytest_addoption(parser):
    parser.addoption(
        "--run-name",
        default=os.environ.get("E2E_RUN_NAME", "local"),
        help="Label for this run's output folder under tests/integration/test-runs/.",
    )
    parser.addoption(
        "--resume",
        action="store_true",
        help="Skip the scenarios that already finished in an interrupted run. "
             "pytest's own --stepwise/--lf only remember FAILURES, so a Ctrl+C "
             "part-way through a green run leaves them with nothing and the next "
             "run starts from the top.",
    )
    parser.addoption(
        "--resume-reset",
        action="store_true",
        help="Forget the recorded progress, so the next run starts from the top.",
    )
    parser.addoption(
        "--dpi",
        type=int,
        default=settings.DEVICE_SCALE_FACTOR,
        help="Screenshot device scale factor. 2 (default) is Retina-sharp; 1 is "
             "a quarter of the file size and noticeably soft on a Retina display.",
    )


@pytest.fixture(scope="session")
def signed_in_state(browser, tmp_path_factory):
    """Sign in ONCE per role, and hand every test the resulting session.

    Driving the login form in all 506 scenarios would spend roughly seventeen
    minutes doing nothing but signing in, and would re-test the one thing
    `suites/01_auth` already covers properly. Instead each role logs in once
    through the real UI — so the flow IS exercised — and Playwright's
    `storage_state` replays that session into every later context.

    Cached per session and per role: at most four logins for a whole run,
    however many scenarios it holds.
    """
    from playwright.sync_api import expect

    from framework.locators import auth as L

    cache: dict[str, str] = {}
    root = tmp_path_factory.mktemp("auth")

    def _login_once(role: str) -> str:
        context = browser.new_context(base_url=settings.BASE_URL)
        try:
            page = context.new_page()
            page.goto("/login")
            page.fill(L.EMAIL, accounts.BY_ROLE[role])
            page.fill(L.PASSWORD, accounts.PASSWORD)
            page.click(L.SIGN_IN)
            expect(page).to_have_url(re.compile(r"/dashboard"), timeout=settings.LOGIN_TIMEOUT_MS)
            path = str(root / f"{role}.json")
            context.storage_state(path=path)
            return path
        finally:
            # Always closed, including on the failed attempt — a leaked context
            # holds a browser page open for the rest of the session and makes
            # the NEXT login slower, which is how one flake becomes several.
            context.close()

    def _state(role: str = "admin") -> str:
        if role not in cache:
            # Retried once. This login gates every test of its role, so a single
            # slow response would fail dozens of unrelated scenarios and read as
            # a product regression rather than the flake it is.
            try:
                cache[role] = _login_once(role)
            except Exception:
                cache[role] = _login_once(role)
        return cache[role]

    return _state


@pytest.fixture
def browser_context_args(browser_context_args, pytestconfig, request, signed_in_state):
    """Deterministic capture, plus an already-signed-in session.

    Function-scoped (pytest-playwright's own is session-scoped) so it can read
    this test's markers and vary the session per test:

        default                     signed in as admin
        @pytest.mark.role("basic")  signed in as that seeded tier
        @pytest.mark.anonymous      no session at all — for the auth scenarios,
                                    which must drive the login form themselves

    A fixed viewport keeps two runs of a scenario comparable.
    `device_scale_factor` is what makes a shot sharp: it defaults to 1, so a
    1440x900 viewport yields a 1440x900 PNG — half of what a Retina display
    shows, and visibly soft at full size.
    """
    args = {
        **browser_context_args,
        "viewport": settings.VIEWPORT,
        "device_scale_factor": pytestconfig.getoption("--dpi"),
        "reduced_motion": "reduce",
    }

    if request.node.get_closest_marker("anonymous"):
        args.pop("storage_state", None)
        return args

    role_marker = request.node.get_closest_marker("role")
    args["storage_state"] = signed_in_state(role_marker.args[0] if role_marker else "admin")
    return args


_RUN_DIR: dict[str, Path] = {}


def run_directory(config) -> Path:
    """`test-runs/<timestamp>-<name>/`, resolved once per session.

    Timestamped rather than id'd: it sorts chronologically, cannot collide, and
    reads as something a human can find again later.

    A plain function and not only a fixture, because `pytest_sessionfinish`
    writes the run report there and hooks cannot request fixtures. Memoised, or
    a session that crosses a minute boundary would write its report into a
    different folder from its screenshots.
    """
    if "path" not in _RUN_DIR:
        stamp = datetime.now().strftime("%Y-%m-%dT%H-%M")
        d = INTEGRATION / "test-runs" / f"{stamp}-{slugify(config.getoption('--run-name'))}"
        d.mkdir(parents=True, exist_ok=True)
        _RUN_DIR["path"] = d
    return _RUN_DIR["path"]


@pytest.fixture(scope="session")
def run_dir(pytestconfig) -> Path:
    return run_directory(pytestconfig)


# pytest-playwright parametrises every test by browser, so a node id reads
# `test_x[chromium]`. That token is noise in a folder name — but a Scenario
# Outline's own params are NOT, and they are what separates one case's
# screenshots from another's. Drop the browser, keep the rest.
_BROWSERS = {"chromium", "firefox", "webkit"}


def _case_name(node) -> str:
    name = re.sub(r"^test_", "", node.name)
    m = re.search(r"\[(.*)\]$", name)
    if not m:
        return name
    params = [p for p in m.group(1).split("-") if p not in _BROWSERS]
    base = name[: m.start()]
    return f"{base}-{'-'.join(params)}" if params else base


# ── live progress ────────────────────────────────────────────────────────────
# A single dot per test says nothing while a run sits on one Bedrock call. These
# hooks print the scenario header and its outcome; `shot()` prints each step in
# between, so the terminal always shows where the suite actually is.


def _title(item) -> str:
    """The Gherkin title, from the test's docstring; its name as a fallback."""
    doc = (getattr(item.function, "__doc__", "") or "").strip().splitlines()
    if doc:
        return doc[0].removeprefix("Scenario:").removesuffix(".").strip()
    return _case_name(item).replace("_", " ")


_progress = {"i": 0, "total": 0}


_results = run_report.Results()


# ── resume after an interrupt ────────────────────────────────────────────────
# A 500-scenario run takes an hour, and a Ctrl+C at minute 50 used to cost all
# fifty. Every scenario that FINISHES is appended here, so --resume can skip it.
# Appended at teardown, one line at a time and flushed, so even a kill -9 loses
# at most the single scenario in flight.
_PROGRESS_FILE = Path(__file__).parent / ".pytest-resume"


def pytest_runtest_logreport(report):
    # teardown, not call: a scenario whose fixtures blew up on the way down is
    # not finished, and must not be skipped on the next pass.
    if report.when == "teardown":
        with _PROGRESS_FILE.open("a") as fh:
            fh.write(report.nodeid + "\n")


def _apply_resume(config, items):
    """Drop the scenarios a previous interrupted run already finished."""
    if config.getoption("--resume-reset"):
        _PROGRESS_FILE.unlink(missing_ok=True)
    if not config.getoption("--resume") or not _PROGRESS_FILE.exists():
        return
    # splitlines(), never split(): 52 of these node ids carry a space inside a
    # parametrised value ("[chromium-Streamed text-uses the agent's raw output]"),
    # and whitespace-splitting shreds them into tokens that match nothing.
    done = {ln.strip() for ln in _PROGRESS_FILE.read_text().splitlines() if ln.strip()}
    keep = [i for i in items if i.nodeid not in done]
    skipped = [i for i in items if i.nodeid in done]
    if not skipped:
        return
    if not keep:
        # Everything on record is done. Start clean rather than collect nothing
        # and report it as "no test ran".
        _PROGRESS_FILE.unlink(missing_ok=True)
        Reporter(config).note(
            f"resume: all {len(skipped)} already finished — progress cleared, running the lot",
            warn=False,
        )
        return
    items[:] = keep
    config.hook.pytest_deselected(items=skipped)
    Reporter(config).note(
        f"resume: skipping {len(skipped)} already finished, {len(keep)} to go", warn=False
    )


def pytest_collection_modifyitems(config, items):
    _apply_resume(config, items)
    _progress["total"] = len(items)
    _results.base_url = config.getoption("--base-url") or "the app"
    _results.run_name = config.getoption("--run-name")
    if items:
        Reporter(config).session(len(items), _results.base_url)


def pytest_deselected(items):
    _results.deselected += len(items)


def pytest_runtest_setup(item):
    _progress["i"] += 1
    marker = item.get_closest_marker("scenario")
    Reporter(item.config).scenario(
        _progress["i"], _progress["total"], marker.args[0] if marker else "UNMARKED", _title(item)
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()

    # A `@pytest.mark.skip` never reaches the call phase, so the report has to
    # be fed from setup too — otherwise every statically skipped scenario is
    # simply absent from the run report, and absent reads as "not written".
    if rep.skipped and rep.when in ("setup", "call"):
        _record(item, "skipped", rep, reason=_skip_reason(rep))
    elif rep.when == "call":
        shooter = getattr(item, "_shooter", None)
        Reporter(item.config).outcome(
            rep.passed, shooter.n if shooter else 0, rep.duration
        )
        _record(item, "passed" if rep.passed else "failed", rep,
                error="" if rep.passed else _short_error(rep))


def _skip_reason(rep) -> str:
    """The reason as written, out of `(path, lineno, "Skipped: <reason>")`."""
    longrepr = getattr(rep, "longrepr", None)
    if isinstance(longrepr, tuple) and len(longrepr) == 3:
        return str(longrepr[2]).removeprefix("Skipped: ").strip()
    return str(longrepr or "").strip()


def _short_error(rep, limit: int = 1200) -> str:
    """The tail of the traceback — where the assertion actually is.

    The head is fixture plumbing every time; the last lines carry the message
    and the locator that timed out, which is the whole diagnostic value.
    """
    text = rep.longreprtext if hasattr(rep, "longreprtext") else str(rep.longrepr)
    text = text.strip()
    return text if len(text) <= limit else "…\n" + text[-limit:]


def _record(item, outcome: str, rep, reason: str = "", error: str = "") -> None:
    if any(c.nodeid == item.nodeid for c in _results.cases):
        return
    marker = item.get_closest_marker("scenario")
    shooter = getattr(item, "_shooter", None)
    _results.add(
        run_report.Case(
            nodeid=item.nodeid,
            suite=Path(item.fspath).parent.name,
            scenario=marker.args[0] if marker else "UNMARKED",
            title=_title(item),
            outcome=outcome,
            reason=reason,
            error=error,
            duration=getattr(rep, "duration", 0.0),
            shots=shooter.n if shooter else 0,
        )
    )


def pytest_sessionfinish(session, exitstatus):
    """Write `0-report.html` at the top of this run's folder."""
    # 0 = all passed, 1 = some failed; either way the run REACHED THE END, so the
    # recorded progress is spent. 2 (interrupted) and 3 (internal error) keep it —
    # that is exactly the case --resume exists for. A --resume run keeps its file
    # too, so a second interrupt is still resumable.
    if exitstatus in (0, 1) and not session.config.getoption("--resume"):
        _PROGRESS_FILE.unlink(missing_ok=True)
    if not _results.cases:
        return
    out = run_report.write(_results, run_directory(session.config))
    Reporter(session.config).note(f"report  {out}", warn=False)


@pytest.fixture(autouse=True)
def dismiss_native_dialogs(page):
    """Dismiss `window.alert` rather than let it block the run.

    Playwright BLOCKS on a native dialog until something handles it, so an
    unhandled alert HANGS the test instead of failing it — and the product
    raises six of them, all download failures (19-toasts-and-dialogs). Autouse
    because the tests that can trigger one are not the tests that expect one:
    any preview or Files-tab interaction can.

    Handlers registered later by a test take precedence, so a scenario that
    wants to READ the alert text can still add its own.
    """
    seen: list[str] = []

    def handle(dialog):
        seen.append(dialog.message)
        dialog.dismiss()

    page.on("dialog", handle)
    page.native_dialogs = seen  # readable by a test that wants to assert on them
    yield seen


@pytest.fixture
def shot(page, run_dir, request) -> Shooter:
    """Screenshot writer bound to this scenario's own folder.

    `test-runs/<run>/<area>/<scenario-id>-<test-name>/NN-slug.png`

    The area is the suite folder — `suites/01_auth/` writes into `01-auth/`,
    matching `screens/01-auth.feature.md` — so a failing shot, the test and the
    spec it came from all carry the same name.
    """
    marker = request.node.get_closest_marker("scenario")
    scenario_id = marker.args[0] if marker else "UNMARKED"

    area = Path(request.node.fspath).parent.name.replace("_", "-", 1)
    out = run_dir / area / f"{scenario_id}-{slugify(_case_name(request.node))}"
    out.mkdir(parents=True, exist_ok=True)

    shooter = Shooter(page, out, scenario_id, request.node.name, Reporter(request.config))
    # Stashed so the makereport hook can report the shot count alongside the
    # outcome — the fixture is gone by then.
    request.node._shooter = shooter
    return shooter


@pytest.fixture
def page_as(browser, signed_in_state, pytestconfig):
    """A second page, signed in as a given role, alongside the test's own.

    For the handful of scenarios that must compare two auth states in one run —
    the bare root branching on token presence, or a tier seeing a screen another
    tier cannot. Contexts are closed when the test ends.
    """
    opened = []

    def _page(role: str = "admin"):
        context = browser.new_context(
            base_url=settings.BASE_URL,
            viewport=settings.VIEWPORT,
            device_scale_factor=pytestconfig.getoption("--dpi"),
            reduced_motion="reduce",
            storage_state=signed_in_state(role),
        )
        opened.append(context)
        return context.new_page()

    yield _page
    for c in opened:
        c.close()


@pytest.fixture
def disposable_user(page_as):
    """Create throwaway accounts through the admin API, and delete them after.

    Several scenarios need a user that can be created, renamed, re-tiered and
    removed without touching a seeded fixture — `seed_test_users.py` owns those
    four, and a test that mutates one poisons every later test of that role.

    **Never `is_admin=True`.** A second local admin trips the break-glass
    invariant and `resolve_principal` then refuses EVERY admin credential,
    including freshly minted ones — the whole suite stops authenticating and the
    only way back is a direct database write. That is D-31, and it cost this
    suite a two-hour outage.

    Yields a factory: `make(tier="hexaware")` -> `{"id", "email", "password"}`.
    """
    from framework import api as _api

    admin = page_as("admin")
    admin.goto("/dashboard")
    created: list[str] = []

    def make(tier: str = "basic", *, email: str | None = None) -> dict:
        address = email or f"e2e-{uuid.uuid4().hex[:12]}@flowinqa.com"
        result = _api.full(
            admin,
            "POST",
            "/api/admin/users",
            {
                "email": address,
                "password": accounts.PASSWORD,
                "tier": tier,
                "is_admin": False,
            },
        )
        assert result["status"] == 201, (
            f"creating a disposable user answered {result['status']}: "
            f"{result['body'][:200]}"
        )
        row = json.loads(result["body"])
        created.append(row["id"])
        return {"id": row["id"], "email": address, "password": accounts.PASSWORD}

    make.admin_page = admin
    yield make

    for user_id in created:
        _api.full(admin, "DELETE", f"/api/admin/users/{user_id}")


# Mints an API key, uses it to create a handoff, and revokes the key — all in
# one round trip inside the browser. The key's plaintext is returned exactly
# once by the create call and is never handed back to Python: only the handoff
# it produced comes out. A key that reached a test process would land in
# steps.json and the CI log the first time an assertion failed.
_MINT_HANDOFF = """
async ([apiUrl, task, repoUrl]) => {
  const token = localStorage.getItem('auth_token');
  const auth = { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token };

  const keyRes = await fetch(apiUrl + '/api/settings/api-keys', {
    method: 'POST', headers: auth,
    body: JSON.stringify({ name: 'e2e-handoff-fixture' }),
  });
  if (keyRes.status !== 201) {
    return { error: 'api-key ' + keyRes.status + ': ' + (await keyRes.text()).slice(0, 200) };
  }
  const key = await keyRes.json();

  let created = null;
  try {
    const res = await fetch(apiUrl + '/api/handoff/receive', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Flowin-API-Key': key.token },
      body: JSON.stringify({ task, repo_url: repoUrl, source_client: 'e2e' }),
    });
    const body = (await res.text()).slice(0, 800);
    created = { status: res.status, body };
  } finally {
    await fetch(apiUrl + '/api/settings/api-keys/' + key.id, {
      method: 'DELETE', headers: auth,
    }).catch(() => {});
  }
  return created;
}
"""


@pytest.fixture
def handoff_session(page_as):
    """Mint a real handoff session, and delete it afterwards.

    `POST /api/handoff/receive` is authenticated by `X-Flowin-API-Key`, not by
    a bearer token — "public" in the endpoint inventory means "no JWT", not "no
    authentication". So a handoff cannot be created without first creating an
    API key, which is why several scenarios across 16, 22 and 24 waited on this
    one fixture.

    Yields a factory: `make(owner="admin")` -> the parsed receive response,
    carrying `token`, `handoff_id`, `url` and `status`.
    """
    from framework import api as _api

    opened: list[tuple] = []

    def make(owner: str = "admin", task: str = "E2E handoff fixture — no work is done") -> dict:
        owner_page = page_as(owner)
        owner_page.goto("/dashboard")
        result = owner_page.evaluate(
            _MINT_HANDOFF,
            [settings.API_URL, task, "https://github.com/flowinqa/e2e-fixture"],
        )
        assert "error" not in result, f"could not mint an API key: {result['error']}"
        assert result["status"] in (200, 201), (
            f"/api/handoff/receive answered {result['status']}: {result['body'][:300]}"
        )
        session = json.loads(result["body"])
        opened.append((owner_page, session))
        return session

    yield make

    # There is no DELETE for a handoff — the API offers receive, read and start
    # and nothing else. They carry an `expires_at` about an hour out and lapse
    # on their own, so the teardown revokes nothing and says so rather than
    # pretending. The API KEY that minted each one is already revoked, inside
    # the same round trip that used it.
    del opened


@pytest.fixture
def sign_in(page):
    """Sign in as a seeded account and land on the dashboard.

    For every test that needs a session but is not itself about signing in. The
    auth scenarios drive the form directly instead — a fixture that hides the
    thing under test proves nothing.
    """
    from playwright.sync_api import expect

    from framework.locators import auth as L

    def _sign_in(role: str = "admin"):
        page.goto("/login")
        page.fill(L.EMAIL, accounts.BY_ROLE[role])
        page.fill(L.PASSWORD, accounts.PASSWORD)
        page.click(L.SIGN_IN)
        expect(page).to_have_url(re.compile(r"/dashboard"))

    return _sign_in
