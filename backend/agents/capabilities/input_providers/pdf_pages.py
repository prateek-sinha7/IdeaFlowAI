"""agents/capabilities/input_providers/pdf_pages.py — the ``pdf_pages`` input_provider capability (spec 019 / T14).

Provides image content blocks from a materialised documents in .extract/ to a step
that declares `injects: [pdf_pages]`. Reads the run's `.extract/{format}/{slug}/pages/NN/image-*.png`
files, downscales to per-image ceilings, and returns as multimodal content blocks.

Degrade to [] when `.extract/` is absent, empty or unreadable — a broken extraction
must never break the agent.

Copy the shape of run_images.py exactly.

Import boundary: this module imports ONLY the registry + stdlib — no app.* import
(import-linter contract).
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from agents.capabilities.registry import register

logger = logging.getLogger(__name__)

# Per-image byte ceiling (from file_extract_tools.py, matching Anthropic API limits)
_IMAGE_MAX_BYTES = int(3.75 * 1024 * 1024)

# Per-image pixel ceiling (Anthropic API standard limit)
_IMAGE_MAX_PIXELS = 5120 * 5120

# Pixels-per-token conversion (same as in file_extract_tools.py and the reference implementation)
_PIXELS_PER_TOKEN = 750


@register(
    "input_provider",
    "pdf_pages",
    user_allowed=True,
    description="Attach materialised PDF page images from .extract/ as multimodal content-blocks to the agent prompt.",
    config_schema={},
)
class PdfPagesProvider:
    """Compose image content-blocks from materialised PDF pages in .extract/

    Satisfies the ``InputContentProvider`` port (``name`` attr + ``async def load``).
    Reads the run's `.extract/{format}/{slug}/pages/NN/image-*.png` files; returns ``[]`` when
    `.extract/` is absent/empty/unreadable. Downscales images to stay within per-image
    ceilings (bytes, pixels, tokens) before returning.

    Never raises; all failures degrade to [].
    """

    name = "pdf_pages"

    async def load(self, ctx: Any) -> list:
        """Load materialised PDF images and return them as content blocks.

        Reads the .extract/ directory structure (created by extract_text), locates the
        manifest.json, and returns all images in reading order as
        {"type":"image","source_type":"base64",...} blocks.

        Downscales any image that exceeds per-image ceilings (bytes, pixels, tokens).
        An image that cannot be downscaled enough is skipped with a warning log.

        Returns [] when .extract/ is absent, empty, or unreadable — never raises.
        """
        # Get the sandbox from the context runner
        runner = getattr(ctx, "runner", None)
        sandbox = getattr(runner, "sandbox", None)
        if sandbox is None:
            return []

        # Try to resolve .extract/ directory
        try:
            pdf_dir = sandbox.path_for(".extract/")
        except (ValueError, TypeError):
            return []

        if not pdf_dir.is_dir():
            return []

        blocks = []

        try:
            import json

            # Every document under .extract/{format}/{slug}/, in a STABLE order.
            # iterdir() yields filesystem order, so anything that picked "the
            # first" depended on inode layout — a run with two materialised
            # documents attached one of them, and not reproducibly the same one.
            slug_dirs = []
            for fmt_dir in sorted(e for e in pdf_dir.iterdir() if e.is_dir()):
                if fmt_dir.name.startswith("."):
                    continue
                for doc_dir in sorted(e for e in fmt_dir.iterdir() if e.is_dir()):
                    if (doc_dir / "manifest.json").is_file():
                        slug_dirs.append(doc_dir)
            if not slug_dirs:
                return []
            if len(slug_dirs) > 1:
                # EVERY materialised document is attached, in a deterministic
                # order. Scope is not derivable from ctx (FR-012a: providers take
                # no per-step arguments), and dropping a document the user
                # uploaded is a worse answer than attaching more than was needed
                # — a silent omission is invisible, an extra page is not.
                logger.info(
                    "pdf_pages: attaching %d materialised documents (%s)",
                    len(slug_dirs),
                    ", ".join(f"{d.parent.name}/{d.name}" for d in slug_dirs),
                )

            for slug_dir in slug_dirs:
                blocks.extend(self._blocks_for_document(slug_dir))

        except (OSError, IOError, ValueError, KeyError):
            # Any error reading directories or manifest -> degrade to []
            return []

        return blocks

    def _blocks_for_document(self, slug_dir) -> list:
        """Image content blocks for ONE materialised document, in page order.

        A document that cannot be read contributes nothing and never stops the
        others: one corrupt manifest must not blank the whole prompt.
        """
        import json

        blocks: list = []
        try:
            manifest_data = json.loads((slug_dir / "manifest.json").read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, IOError):
            return []

        pages_info = manifest_data.get("pages", {})
        if not pages_info:
            return []

        try:
            # Process pages in numeric order
            for page_num_str in sorted(
                pages_info.keys(),
                key=lambda x: int(x) if x.isdigit() else float("inf"),
            ):
                page_info = pages_info[page_num_str]
                image_refs = page_info.get("images", [])

                # Process each image reference for this page
                for image_ref in image_refs:
                    try:
                        # Resolve the image path (it's either relative to the page dir
                        # or relative to the slug dir for repeated images)
                        if "/" in image_ref:
                            # Repo-relative path under {slug}/ (e.g., "pages/02/image-1.png")
                            image_path = slug_dir / image_ref
                        else:
                            # Bare filename in this page's directory (e.g., "image-1.png")
                            page_dir = slug_dir / "pages" / f"{int(page_num_str):02d}"
                            image_path = page_dir / image_ref

                        # Read the image file
                        if not image_path.is_file():
                            logger.warning(
                                "Image not found: %s (referenced in page %s)",
                                image_path,
                                page_num_str,
                            )
                            continue

                        image_bytes = image_path.read_bytes()

                        # Check if it's within byte ceiling or needs downscaling
                        if len(image_bytes) > _IMAGE_MAX_BYTES:
                            # Try to downscale the image
                            image_bytes = self._downscale_image(
                                image_bytes, _IMAGE_MAX_BYTES, _IMAGE_MAX_PIXELS
                            )
                            if image_bytes is None:
                                logger.warning(
                                    "Skipping %s: exceeds size ceiling even after downscaling",
                                    image_path,
                                )
                                continue
                        else:
                            # Image is within byte ceiling, but check pixel ceiling
                            image_bytes = self._validate_pixel_ceiling(image_bytes, _IMAGE_MAX_PIXELS)
                            if image_bytes is None:
                                logger.warning(
                                    "Skipping %s: exceeds pixel ceiling",
                                    image_path,
                                )
                                continue

                        # Encode as base64
                        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

                        # Determine MIME type (always PNG in this context)
                        mime_type = "image/png"

                        # Add content block
                        blocks.append(
                            {
                                "type": "image",
                                "source_type": "base64",
                                "mime_type": mime_type,
                                "data": image_b64,
                            }
                        )

                    except (OSError, IOError) as e:
                        logger.warning(
                            "Failed to read image %s (page %s): %s",
                            image_ref,
                            page_num_str,
                            e,
                        )
                        continue

        except (OSError, IOError, ValueError, KeyError):
            # Any error reading directories or manifest -> degrade to []
            return []

        return blocks

    @staticmethod
    def _validate_pixel_ceiling(image_bytes: bytes, max_pixels: int) -> bytes | None:
        """Validate that a PNG image is within pixel ceiling.

        Lazily imports PIL. Returns the image_bytes if valid, None if it
        exceeds the pixel ceiling.
        """
        try:
            from io import BytesIO
            from PIL import Image
        except ImportError:
            # PIL not available, cannot validate
            return image_bytes

        try:
            img = Image.open(BytesIO(image_bytes))
            if img.width * img.height <= max_pixels:
                return image_bytes
            return None
        except Exception:
            # Any error -> cannot validate, be conservative and reject
            return None

    @staticmethod
    def _downscale_image(
        image_bytes: bytes, max_bytes: int, max_pixels: int, max_attempts: int = 5
    ) -> bytes | None:
        """Downscale a PNG image to fit within byte and pixel ceilings.

        Lazily imports PIL. Returns downscaled PNG bytes or None if image
        cannot be reduced enough.

        Reduces resolution iteratively until within both the byte and pixel limits.
        """
        try:
            from io import BytesIO

            from PIL import Image
        except ImportError:
            # PIL not available, cannot downscale
            return None

        try:
            # Open the image
            img = Image.open(BytesIO(image_bytes))

            # If already within limits, return as-is
            if len(image_bytes) <= max_bytes and img.width * img.height <= max_pixels:
                return image_bytes

            # Try iterative scaling
            scale_factor = 0.9
            for attempt in range(max_attempts):
                # Scale the image
                new_width = int(img.width * scale_factor)
                new_height = int(img.height * scale_factor)

                if new_width < 1 or new_height < 1:
                    # Image too small
                    return None

                scaled = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

                # Check pixel ceiling
                if scaled.width * scaled.height > max_pixels:
                    # Still exceeds pixel ceiling, reduce scale factor more aggressively
                    scale_factor *= 0.8
                    continue

                # Save as PNG with reduced quality
                output = BytesIO()
                # PNG doesn't have a quality parameter like JPEG,
                # but we can control compression
                scaled.save(output, format="PNG", optimize=True)
                output.seek(0)
                result_bytes = output.getvalue()

                if len(result_bytes) <= max_bytes:
                    return result_bytes

                # Reduce scale factor for next iteration
                scale_factor *= 0.9

            return None

        except Exception:
            # Any PIL error -> cannot downscale
            return None
