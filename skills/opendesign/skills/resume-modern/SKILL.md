---
name: resume-modern
zh_name: "Minimalist Resume"
en_name: "Modern Resume"
emoji: "📄"
description: "Modern minimalist resume, single A4 page, suitable for printing or exporting to PDF"
category: resume
scenario: personal
aspect_hint: "A4 (210×297mm)"
recommended: 12
tags: ["resume", "cv", "curriculum-vitae"]
example_id: sample-resume-frontend
example_name: "Minimalist Resume · Frontend Engineer"
example_format: markdown
example_tagline: "Single A4 page, printable / exportable to PDF"
example_desc: "Senior frontend engineer resume, two-column layout, highlighted quantified achievements"
od:
  mode: prototype
  surface: web
  platform: desktop
  scenario: personal
  featured: 12
  upstream: "https://github.com/nexu-io/html-anything"
  preview:
    type: html
    entry: index.html
    reload: debounce-100
  design_system:
    requires: false
  example_prompt: "Use the \"Minimalist Resume\" template to turn my content into a \"modern minimalist resume, single A4 page, suitable for printing or exporting to PDF.\" Keep the template's visual signature, use real content and data, and avoid lorem ipsum and placeholder images."
---

[Template: Modern Minimalist Resume]
- Container width simulates A4: `w-[210mm] min-h-[297mm] mx-auto`, padding 16-20mm.
- Large name at the top (text-4xl), a contact line below (email / phone / city / GitHub / LinkedIn), separated by thin vertical dividers.
- Optional two-column body: left 60% primary column (experience/projects/education), right 40% secondary column (skills/languages/awards).
- Section headings: small caps style, with a short accent line above (w-8 h-0.5).
- Each experience entry: company + role + date range (right-aligned), followed by 1-3 bullets starting with verbs.
- No flashy colors — black/white/gray plus 1 accent (deep blue / dark green).
- Add @media print styles, hide unnecessary elements, keep colors.
