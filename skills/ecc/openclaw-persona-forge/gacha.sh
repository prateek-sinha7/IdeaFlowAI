#!/bin/bash
# Lobster Soul Gacha Machine - thin shell wrapper
# Actual logic lives in gacha.py (Python secrets module guarantees true randomness)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec python3 "${SCRIPT_DIR}/gacha.py" "$@"
