#!/bin/bash
# Shared entry point. Harbor always runs tests/test.sh; the stage-specific
# logic lives in test_outputs.py, the shared helpers in verifier.py.
python3 /tests/test_outputs.py
