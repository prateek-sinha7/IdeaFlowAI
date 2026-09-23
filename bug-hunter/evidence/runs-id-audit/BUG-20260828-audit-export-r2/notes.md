UI shows two distinct on-screen category badges: "Gate" for governance rows and
"Security" for secret-scan rows (pill counts: Governance 96, Security 4).

Export menu copy (Export dropdown) promises:
  CSV — "flattened rows timestamp · agent · category · event · outcome · severity"
  JSON — "raw rows incl. category · step · outcome · severity · timestamp"

Actual downloaded files (03-export.csv, 04-export.json, both same run, 100 rows):
  - category field == "gate" for ALL 100 rows, including the 4 rows the UI badges
    "Security" (Secret scan — scanned before write). The Security/Governance split
    visible in the UI is lost entirely in both export formats.
  - severity field == "" (empty string) for ALL 100 rows in both formats, despite
    the page's persistent footer promising "every entry carries severity + timestamp"
    and the export menu itself listing severity as an included column.

Verified via:
  python3 -c "import csv; ... set(row['severity'] for row in rows)" -> {''}
  python3 -c "import csv; ... set(row['category'] for row in rows)" -> {'gate'}
  Same check against the JSON file gives identical results.
