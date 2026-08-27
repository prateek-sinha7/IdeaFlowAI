"""Call the backend as the signed-in user, without ever handling their token.

Some scenarios assert the SERVER's behaviour rather than the screen's — that a
locked pipeline is refused at launch, that a run is unreadable across an
ownership boundary. Those need an authenticated request.

The request is made **inside the browser**, by `fetch` from the page's own
origin, and only the status and a small slice of the body come back. The
alternative — reading `localStorage.getItem('auth_token')` into Python — would
pull a live bearer credential into the test process, where a failing assertion
prints it into `steps.json` and the CI log. It never leaves the browser here.
"""

from __future__ import annotations

import json

from framework import settings

# Same origin the app itself calls: the frontend talks to the backend directly
# at ENV.API_URL rather than through a Next.js rewrite, so the browser already
# holds a working CORS relationship with it.
_FETCH = """
async ([method, url, body]) => {
  const token = localStorage.getItem('auth_token');
  const res = await fetch(url, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: 'Bearer ' + token } : {}),
    },
    ...(body ? { body } : {}),
  });
  let text = '';
  try { text = (await res.text()).slice(0, 400); } catch (e) { /* no body */ }
  return { status: res.status, body: text };
}
"""


def request(page, method: str, url: str, body: dict | None = None) -> dict:
    """`{status, body}` for a call made as the page's signed-in user.

    `body` is truncated to 400 characters: enough to assert on an error message,
    short enough that a large payload cannot flood a step's metadata.
    """
    if url.startswith("/"):
        # Absolute, always. A relative path reaches the Next.js origin and comes
        # back 200 with a page — which reads as "the endpoint allowed it".
        url = settings.API_URL + url
    return page.evaluate(_FETCH, [method, url, json.dumps(body) if body else None])
