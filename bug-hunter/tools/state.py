#!/usr/bin/env python3
"""Update bug-hunter/hunt-state.md rows. Usage:
  state.py start <slug> <worker> "<focus>"
  state.py done  <slug> FOUND_BUG|NO_NEW_BUG|BLOCKED ["<note>"]
  state.py board            # summary counts
"""
import sys, pathlib
P = pathlib.Path(__file__).resolve().parent.parent / 'hunt-state.md'  # tools/ -> bug-hunter/
lines = P.read_text().split('\n')

def rows():
    for i, l in enumerate(lines):
        if l.startswith('| p'):
            yield i, [c.strip() for c in l.strip('|').split('|')]

def write(i, c):
    lines[i] = '| ' + ' | '.join(c) + ' |'

cmd = sys.argv[1]
if cmd == 'board':
    from collections import Counter
    st = Counter(c[9] for _, c in rows())
    bugs = sum(int(c[6]) for _, c in rows())
    print(dict(st), 'bugs_filed=', bugs)
    sys.exit()

slug = sys.argv[2]
for i, c in rows():
    if c[3] != slug:
        continue
    if cmd == 'start':
        c[4] = str(int(c[4]) + 1); c[5] = sys.argv[3]; c[9] = 'ACTIVE'
        c[10] = sys.argv[4] if len(sys.argv) > 4 else c[10]
    else:
        res = sys.argv[3]; c[5] = '—'
        if res == 'FOUND_BUG':
            c[6] = str(int(c[6]) + 1); c[7] = '0'; c[9] = 'READY'
        elif res == 'NO_NEW_BUG':
            c[7] = str(int(c[7]) + 1); c[8] = '0'
            c[9] = 'CONVERGED' if int(c[7]) >= 2 else 'READY'
        else:
            c[8] = str(int(c[8]) + 1)
            c[9] = 'BLOCKED' if int(c[8]) >= 2 else 'READY'
        if len(sys.argv) > 4:
            c[10] = (c[10] + '; ' if c[10] != '—' else '') + sys.argv[4]
    write(i, c); P.write_text('\n'.join(lines)); print('ok', slug, c[9], 'round', c[4], 'bugs', c[6], 'clean', c[7])
    break
else:
    sys.exit('slug not found: ' + slug)
