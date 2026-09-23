# The integration suite

Implements `../screens/*.feature.md`. One test per Gherkin scenario, linked by a
stable id that `../capture/_scenarios.py` checks in both directions.

## Layout

```
e2e/
├── pytest.ini              the live/offline split, timeouts, markers
├── requirements.txt        this suite's deps only, not the backend's
├── conftest.py             fixtures — must sit at the rootdir to be visible
├── framework/              shared machinery, knows about no single screen
│   ├── shot.py             the screenshot + steps.json writer
│   ├── accounts.py         seeded QA accounts
│   └── locators/           selectors, one module per spec area
│       ├── auth.py             <- screens/01-auth.feature.md
│       └── shell.py            the chrome wrapping every screen
└── suites/                 the tests, one folder per spec area
    └── 01_auth/
        └── test_signin.py
```

`suites/<NN_area>/` mirrors `screens/NN-area.feature.md` and the run output's
`NN-area/` folder — a failing screenshot, the test and the spec all carry the
same name.

An area is a folder rather than a file so it can be split when it grows.
`23-controls-inventory` is 57 scenarios and `07-run-detail` is 36; those belong
in several files, not one.

**Selectors live in `framework/locators/`, not in the suite folders.** 24 files
all named `locators.py` collide the moment two are importable at once — which is
also why `pytest.ini` sets `--import-mode=importlib`, so two suites may each
hold a `test_tabs.py`.

Never name a module `selectors.py`: that shadows the stdlib module asyncio
imports.

## Running

```bash
uv venv .venv
uv pip install -p .venv -r requirements.txt

.venv/bin/python -m pytest                       # offline suite
.venv/bin/python -m pytest --headed              # watch it drive
.venv/bin/python -m pytest suites/01_auth        # one area
.venv/bin/python -m pytest -m live               # real Bedrock — costs money
```

Needs the frontend on :3000 and the backend on :8000, plus the seeded QA
accounts (`backend/scripts/seed_test_users.py`). Both that script and
`framework/accounts.py` read `E2E_BASE_PASSWORD`; set it for one and not the
other and every sign-in fails confusingly.

No `playwright install` step — `--browser-channel chrome` drives the real
Google Chrome already on the machine, not a downloaded Chromium.

## Output

```
../test-runs/<timestamp>-<name>/<area>/<scenario-id>-<test-name>/
├── 01-sign-in-form.png
├── 02-credentials-entered.png
├── 03-dashboard.png
└── steps.json
```

`steps.json` carries, per shot: the Gherkin line, the URL, console errors,
failed requests, outcome and duration. A bare PNG makes a later reader guess
what it was meant to prove.

A failing step still shoots — `NN-slug-FAILED.png` — then re-raises. `steps.json`
is rewritten after every shot, so a hard crash still leaves what was collected.

**A run is green when pytest exits 0.** The screenshots are evidence, never the
pass/fail signal.

**Nothing ever deletes `test-runs/`.** Each run adds a new timestamped folder;
none is pruned, rotated or overwritten. Clearing old runs is the user's call —
comparing this run's screenshots against last week's is why they are kept. The
folder is gitignored, so it costs nothing but disk.

### Screenshot quality — `framework/settings.py`

**Every capture and timing knob lives in that one file.** When shots come out
blurry, half-painted or full of skeletons, that is the only place to change —
nothing else hard-codes a timeout, a viewport or a spinner selector. Each value
is overridable from the environment, so a slow machine needs no code edit.

| | Default | Why |
|---|---|---|
| `DEVICE_SCALE_FACTOR` | `2` | Playwright defaults to **1**, producing a 1440x900 PNG for a 1440x900 viewport — half the resolution a Retina display shows, and visibly soft at full size |
| `VIEWPORT` | 1440x900 | fixed, so two runs of a scenario are comparable |
| `SETTLE_MS` | 5000 | ceiling on waiting for the document to finish painting |
| `BUSY_TIMEOUT_MS` | 8000 | ceiling on waiting for loading affordances to clear |
| `BUSY_SELECTORS` | see file | anything visible here means the app is still working |

**`BUSY_SELECTORS` is the one to grow.** The `load` event fires when the
*document* is done, which on a client-rendered app is well before the *data* is.
That gap is what puts skeleton cards and a "Loading workspace…" toast into an
otherwise correct screenshot. Every shot waits for all of these to disappear:

```python
"text=Loading workspace…"   # store/GlobalPreloadIndicator.tsx
".animate-pulse"            # Tailwind skeleton
".animate-spin"             # spinner icon
'[aria-busy="true"]'
'[data-loading="true"]'
```

When a new loading affordance shows up in a screenshot, **add it here** — that
is the fix, not a `sleep()` in the test.

`networkidle` is deliberately never used: the Next.js dev server holds an open
HMR websocket, so the network is never idle and that wait would burn its full
timeout on every shot.

Shots are also taken with `animations="disabled"`, which finishes any CSS
transition instantly and pins infinite ones to their first frame — otherwise a
shot landing mid-fade catches it half-done.

2x costs about 180 KB a shot instead of 70 KB. Since runs are never pruned, a
full 506-scenario sweep is roughly 270 MB rather than 105 MB. Drop it when that
matters:

```bash
sh tests/integration/scripts/run-all-offline.sh --dpi 1
```

## Writing a test

```python
@pytest.mark.scenario("S-01-02")
def test_signing_in_with_valid_credentials_lands_on_the_dashboard(page, shot):
    with shot("dashboard", 'Then the URL becomes "/dashboard"'):
        page.click(L.SIGN_IN)
        expect(page).to_have_url(re.compile(r"/dashboard"))
```

Put the assertion **inside** the block. `expect()` polls until it matches, so it
is both the wait and the check, and the screenshot lands on the settled state.
Never `sleep()`.

Assert on process and static UI text; never on model-generated content. A deck's
wording changes every run — that the run reached `completed` with a deliverable
does not.
