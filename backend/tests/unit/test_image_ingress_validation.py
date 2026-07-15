"""Unit tests for `_validate_images` — the image-input ingress chokepoint.

Covers the caps (mime allow-list, per-image raw size, count, aggregate) and the
vision guard (IMAGE-INPUT §3 Layer 1/5, §12 F3; threats T-frv-01 / T-frv-02).
Mirrors the `_validate_model_overrides` unit-test import pattern. Test-file
model-id literals are fine here — `tests/` is NOT scanned by
`test_single_source_grep`.
"""

from __future__ import annotations

import base64

from app.api.run_engine import (
    _IMAGE_MAX_AGGREGATE_BYTES,
    _IMAGE_MAX_BYTES_PER_IMAGE,
    _IMAGE_MAX_COUNT,
    _validate_images,
)

# A real vision=True catalog id (Haiku 4.5).
_VISION_MODEL = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"


def _b64_for_raw_bytes(raw_len: int) -> str:
    """Return a base64 string whose decoded length is ~`raw_len` bytes.

    `_validate_images` estimates raw bytes as `len(data) * 3 // 4`, so we build a
    base64 payload of the right length directly.
    """
    return base64.b64encode(b"\x00" * raw_len).decode("ascii")


def _small_png() -> dict:
    return {"name": "x.png", "mime_type": "image/png", "data": _b64_for_raw_bytes(64)}


# --- empty / no-op ----------------------------------------------------------


def test_empty_is_noop() -> None:
    assert _validate_images([]) is None
    assert _validate_images(None) is None
    assert _validate_images([], effective_model_ids={_VISION_MODEL}) is None


# --- malformed ---------------------------------------------------------------


def test_non_list_rejected() -> None:
    assert _validate_images("evil_string") is not None
    assert _validate_images({"mime_type": "image/png", "data": "AAAA"}) is not None


def test_non_dict_entry_rejected() -> None:
    err = _validate_images(["not-a-dict"])
    assert err is not None and "must be an object" in err


def test_missing_or_non_string_fields_rejected() -> None:
    assert _validate_images([{"mime_type": "image/png"}]) is not None  # no data
    assert _validate_images([{"data": "AAAA"}]) is not None  # no mime
    assert _validate_images([{"mime_type": 123, "data": "AAAA"}]) is not None
    assert _validate_images([{"mime_type": "image/png", "data": 123}]) is not None


# --- mime allow-list ---------------------------------------------------------


def test_bad_mime_rejected_naming_the_mime() -> None:
    err = _validate_images([{"mime_type": "image/svg+xml", "data": "AAAA"}])
    assert err is not None and "image/svg+xml" in err


def test_all_allowed_mimes_accepted() -> None:
    for mime in ("image/png", "image/jpeg", "image/webp", "image/gif"):
        err = _validate_images([{"mime_type": mime, "data": _b64_for_raw_bytes(64)}])
        assert err is None, f"{mime} unexpectedly rejected: {err}"


# --- per-image size cap ------------------------------------------------------


def test_oversized_single_image_rejected() -> None:
    oversized = _b64_for_raw_bytes(_IMAGE_MAX_BYTES_PER_IMAGE + 4096)
    err = _validate_images([{"mime_type": "image/png", "data": oversized}])
    assert err is not None and "too large" in err


def test_image_at_cap_accepted() -> None:
    at_cap = _b64_for_raw_bytes(_IMAGE_MAX_BYTES_PER_IMAGE - 1024)
    err = _validate_images([{"mime_type": "image/png", "data": at_cap}])
    assert err is None


# --- count cap ---------------------------------------------------------------


def test_over_count_rejected() -> None:
    images = [_small_png() for _ in range(_IMAGE_MAX_COUNT + 1)]
    err = _validate_images(images)
    assert err is not None and "too many images" in err


def test_at_count_accepted() -> None:
    images = [_small_png() for _ in range(_IMAGE_MAX_COUNT)]
    assert _validate_images(images) is None


# --- aggregate cap -----------------------------------------------------------


def test_aggregate_over_cap_rejected_even_when_each_under_per_image() -> None:
    # Each image ~3 MB (under the 3.75 MB per-image cap) but 4 of them (~12 MB)
    # exceed the 8 MB aggregate cap.
    per_image_raw = 3 * 1024 * 1024
    assert per_image_raw < _IMAGE_MAX_BYTES_PER_IMAGE
    one = {"mime_type": "image/png", "data": _b64_for_raw_bytes(per_image_raw)}
    images = [dict(one) for _ in range(4)]
    total = per_image_raw * 4
    assert total > _IMAGE_MAX_AGGREGATE_BYTES
    err = _validate_images(images)
    assert err is not None and "aggregate" in err


# --- vision guard ------------------------------------------------------------


def test_valid_set_with_vision_model_accepted() -> None:
    images = [_small_png(), _small_png()]
    assert _validate_images(images, effective_model_ids={_VISION_MODEL}) is None


def test_non_catalog_model_rejected() -> None:
    images = [_small_png()]
    err = _validate_images(
        images, effective_model_ids={"evil.attacker/raw-config-model:latest"}
    )
    assert err is not None and "vision-capable" in err


def test_mixed_vision_and_non_catalog_rejected() -> None:
    images = [_small_png()]
    err = _validate_images(
        images, effective_model_ids={_VISION_MODEL, "not-a-model"}
    )
    assert err is not None


def test_all_catalog_ids_are_vision_capable() -> None:
    from agents.capabilities.model_catalog import ModelCatalog

    ids = set(ModelCatalog().ids())
    images = [_small_png()]
    # Every real catalog id passes the vision guard.
    assert _validate_images(images, effective_model_ids=ids) is None
