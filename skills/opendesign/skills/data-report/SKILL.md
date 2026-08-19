---
name: data-report
zh_name: "Data Visualization Report"
en_name: "Data Visualization Report"
emoji: "📊"
description: "Turn CSV/Excel/JSON data into a polished visualization report page"
category: data
scenario: finance
aspect_hint: "desktop long page"
featured: 10
tags: ["data", "report", "chart", "data visualization", "analytics report"]
example_id: sample-data-weekly-report
example_name: "Data Report · Weekly Report"
example_format: csv
example_tagline: "KPI cards + Chart.js charts + table"
example_desc: "Nine months of growth data automatically rendered into a visualization report, with inline Chart.js"
od:
  mode: prototype
  surface: web
  platform: desktop
  scenario: finance
  featured: 10
  upstream: "https://github.com/nexu-io/html-anything"
  preview:
    type: html
    entry: index.html
    reload: debounce-100
  design_system:
    requires: false
  example_prompt: "Use the 'Data Visualization Report' template to turn my content into a 'page that turns CSV/Excel/JSON data into a polished visualization report'. Keep the template's visual signature, use real content and data, and avoid lorem ipsum and placeholder images."
---

[Template: Data Visualization Report]
- Header: report title + time range + data source description.
- KPI card grid: 3-5 of the most important metrics, each card showing the value + year-over-year change + a mini trend line.
- Main chart area: at least 2 charts (bar / line / pie / scatter), using Chart.js or ECharts (loaded via jsdelivr CDN), with data parsed from user input.
- **Chart containers must have a fixed height**: wrap each `<canvas>` in a `<div style="position:relative;height:NNNpx">` (KPI mini-charts ~40px, main charts ~240-280px). When Chart.js uses `responsive:true, maintainAspectRatio:false` without an explicit height on the parent container, it falls into a ResizeObserver infinite loop, growing the chart until it freezes the browser. **Never** set a `height=` attribute directly on the canvas as layout — that is only an initial value.
- Data table: an excerpt of the user's raw data, using `<table>` with modern styling (zebra stripes, hover, sticky header).
- Insights block: 3-5 text insights, each starting with an emoji, styled like a product weekly report.
- A collapsible "Methodology" section at the bottom.
- Restrained, professional color palette: 1 primary color + a neutral scale, with a chart palette.
- **Must parse the actual data the user provides** — do not fabricate it.
