#!/usr/bin/env python3
"""Print captured screen fingerprints compactly. Usage: _dump.py <file.json> [...]"""
import json
import sys

for path in sys.argv[1:]:
    print("#" * 8, path)
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    for k, v in d.items():
        if k == "text":
            print("TEXT:")
            print(v[:1800])
        else:
            print(k.upper() + ":", json.dumps(v)[:1000])
    print()
