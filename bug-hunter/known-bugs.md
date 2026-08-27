# Known Bugs

Canonical shared ledger for the autonomous browser bug hunt against Velocity (local dev,
`http://localhost:3000`).

Workers MUST read this file in full before any browser interaction, and MUST re-read it while
holding `bug-hunter/known-bugs.lock` immediately before recording a newly discovered issue.

Append only. Never rewrite or delete an existing entry. Evidence for each bug lives in
`bug-hunter/evidence/<page-slug>/<BUG-ID>/`. See `bug-hunter/README.md` for the full contract.

---

<!-- Bugs are appended below this line, newest last. -->
