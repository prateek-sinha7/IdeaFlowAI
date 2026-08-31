"""tests/unit/test_iss118_construct_only_exemptions.py — the exemption dict is an
inventory of unfixed tests, not a fix (ISS-118).

``tests/conftest.py::_CONSTRUCTS_BUT_NEVER_INVOKES`` totally exempts eight nodeids
from the ISS-102 / FIX-238 live-model-client guard: for those tests
``_forbid_live_model_clients`` returns before patching any provider ``__init__``,
so the real class is left untouched. That is fine *only* while the test never
invokes the client it constructs — the moment one of them adds ``.ainvoke`` /
``.astream``, the guard that exists to stop exactly that has already opted out
and the call goes live.

The card's fix shape: each of the eight should stub its own construction seam
(the way ``tests/unit/test_model_factory.py:77/83/89`` already does) so the
exemption can be deleted entirely, restoring guard coverage to the whole suite.
"""

from __future__ import annotations

import pytest

from tests.conftest import _CONSTRUCTS_BUT_NEVER_INVOKES


@pytest.mark.issue("ISS-118")
def test_no_offline_test_is_globally_exempt_from_the_live_model_guard():
    """Every offline test must stub its construction seam, not opt out of the guard.

    A non-empty ``_CONSTRUCTS_BUT_NEVER_INVOKES`` means at least one test builds a
    real LLM provider client with the ISS-102 guard fully disabled for its nodeid —
    an ``.ainvoke``/``.astream`` added to that test later would be live spend with
    no guard left to catch it.
    """
    assert _CONSTRUCTS_BUT_NEVER_INVOKES == {}, (
        f"{len(_CONSTRUCTS_BUT_NEVER_INVOKES)} test(s) bypass the ISS-102 guard "
        "entirely via _CONSTRUCTS_BUT_NEVER_INVOKES instead of stubbing their "
        "construction seam (ISS-118): "
        f"{sorted(_CONSTRUCTS_BUT_NEVER_INVOKES)}"
    )
