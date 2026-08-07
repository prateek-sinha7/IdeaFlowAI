---
id: TEST-27
type: test
status: done
area: [sse, agents, auth]
summary: >-
  TS-L — Token usage (TokenUsageSummary)
source: .planning/TEST-REGISTER.md#ts-l-token-usage-tokenusagesummary
covers: [TS-L-01, TS-L-02, TS-L-03, TS-L-04]
---

### TS-L — Token usage (TokenUsageSummary)

| ID | Title | Steps | Expected | Status |
|---|---|---|---|---|
| TS-L-01 | Summary card | on complete | header `Token Usage` + `{X}K total`; breakdown `{X} input` / `{Y} output`; ratio bar; cost row `Est. cost ({model})` | 🔴 |
| TS-L-02 | Number formats | various totals | `formatTokens`: ≥1M `{n}M`, ≥1000 `{n}K`, else raw; assert regex `/[\d.]+[KM]? total/` | 🔴 |
| TS-L-03 | Cost formats | zero / tiny / normal | `0`→`—`; `<0.001`→`<$0.001`; else `~$X.XXX` | 🔴 |
| TS-L-04 | Per-agent token pill | DONE cards | `{X}K tokens` (mono) when total>0 | 🔴 |
