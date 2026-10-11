#!/usr/bin/env python3
"""Scan for projection reads of is_admin and tier in decision contexts."""

import os
import re
import sys

# Scan app directory for projection reads
projection_pattern = r"\b(is_admin|tier)\b"
exclude_dirs = {"models", "schemas", "tests", "__pycache__"}
exclude_files = {"provisioning.py"}

hits = []

for root, dirs, files in os.walk("app"):
    # Remove excluded directories
    dirs[:] = [d for d in dirs if d not in exclude_dirs]

    for file in files:
        if not file.endswith(".py") or file in exclude_files:
            continue

        if "provisioning" in root:
            continue

        filepath = os.path.join(root, file)

        try:
            with open(filepath, "r", errors="ignore") as f:
                for line_num, line in enumerate(f, 1):
                    if not line.strip().startswith("#") and re.search(
                        projection_pattern, line
                    ):
                        hits.append((filepath, line_num, line.rstrip()))
        except Exception as e:
            print(f"Error reading {filepath}: {e}", file=sys.stderr)

# Print first 50 hits
for filepath, line_num, line in hits[:50]:
    print(f"{filepath}:{line_num}:{line[:120]}")

print(f"\nTotal hits: {len(hits)}", file=sys.stderr)
