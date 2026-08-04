<spec>
# Prototype Specification: Ledgerline — Expense Approval Console

## Template & Design System
- **Template**: none active — blank-canvas mode, full class system defined below
- **Design System**: Ledgerline Slate — cool paper-white surfaces, deep indigo accent, tabular numerals everywhere money appears, compact operational density
- **CSS Class System**: `.sidebar`, `.nav-link`, `.main`, `.page`, `.page-header`, `.page-title`, `.filter-group`, `.filter-btn`, `.table-wrap`, `.table`, `.amount`, `.badge`, `.badge-pending`, `.badge-approved`, `.badge-rejected`, `.card`, `.grid-2`, `.detail-list`, `.action-row`, `.btn`, `.btn-approve`, `.btn-reject`, `.form-group`, `.form-label`, `.form-input`, `.empty-note`
- **Color Tokens**: --bg=#f7f7f9, --fg=#1f2430, --accent=#3b4bd8, --surface=#ffffff, --border=#e2e4ea, --muted=#6b7280

## Overview
- **Product**: Internal expense-approval console for the finance team at Ledgerline
- **Target audience**: The two finance approvers who clear the submission queue each morning
- **Core purpose**: Triage the expense inbox by status, open any expense, and approve or reject it with the status visibly updated
- **Total pages**: 4 (Inbox, Expense Detail, Reports, Settings)

## Pages & Navigation
| Page ID | Route | Purpose | Layout Pattern | Entry Point |
|---------|-------|---------|----------------|-------------|
| inbox | `#/inbox` | Expense queue with status filter buttons | filter bar + full-width table | Yes |
| expense-detail | `#/expense/:id` | One expense with Approve / Reject actions, rendered for the clicked row | two-column detail cards + action row | No |
| reports | `#/reports` | Total spend by category, consistent with the inbox data | full-width summary table | No |
| settings | `#/settings` | Approval policy preferences | stacked form card | No |

## Page Specifications

### Inbox (`#/inbox`)
**Layout**: status filter bar above a full-width expense table
**Template classes**: `.page-header`, `.filter-group`, `.filter-btn`, `.table-wrap`, `.table`, `.amount`, `.badge`
**Components**:
  - Status filter: four buttons — All, Pending, Approved, Rejected — exactly one active at a time, re-filtering the table on click
  - Expense table: columns [Expense, Merchant, Amount, Category, Submitted, Employee, Status], 5 rows:
    - EXP-2201, Delta Air Lines, $482.30, Travel, 2026-03-02, Sofia Marin, Pending
    - EXP-2202, Atlassian (Jira licences), $683.76, Software, 2026-03-03, James Cho, Approved
    - EXP-2203, Blue Bottle Coffee (client meeting), $58.42, Meals, 2026-03-04, Priya Patel, Pending
    - EXP-2204, Office Depot (standing desks), $1,207.95, Office, 2026-03-05, Miguel Torres, Rejected
    - EXP-2205, Lyft (airport transfer), $63.18, Travel, 2026-03-06, Sofia Marin, Approved
  - Empty-state note: when the active filter matches nothing, one row spans the table saying "No expenses in this state."
**Interactions**:
  - clicking a filter button → re-filters the table and moves the active highlight
  - clicking an expense row → navigates to `#/expense/{id}` for that row
  - approving or rejecting on the detail page → this table shows the new status on return

### Expense Detail (`#/expense/:id`)
**Layout**: page header with the expense id and merchant, two cards (submission, receipt summary), then the action row
**Template classes**: `.page-header`, `.grid-2`, `.card`, `.detail-list`, `.badge`, `.action-row`, `.btn-approve`, `.btn-reject`
**Components**:
  - Submission card: merchant, amount, category, submitted date, employee, cost centre — from the store for the `:id` in the route (2201–2205)
  - Receipt summary card: payment method, receipt reference, approver note field state
  - Status badge in the header reflecting the expense's CURRENT status
  - Action row: Approve button and Reject button; each sets the expense's status in the store and updates the header badge immediately, without navigation
  - Back link: "← Back to inbox" navigating to `#/inbox`
**Interactions**:
  - the page renders whichever expense id the route carries — five distinct records, never one hardcoded expense
  - Approve → status becomes Approved, badge re-renders on the spot
  - Reject → status becomes Rejected, badge re-renders on the spot
  - back link → navigates to `#/inbox`, which reflects the changed status

### Reports (`#/reports`)
**Layout**: full-width summary table under a page header
**Template classes**: `.page-header`, `.table-wrap`, `.table`, `.amount`
**Components**:
  - Category totals table: columns [Category, Expenses, Total], derived from the same five expenses:
    - Travel, 2, $545.48
    - Software, 1, $683.76
    - Meals, 1, $58.42
    - Office, 1, $1,207.95
  - Grand-total row: 5 expenses, $2,495.61
**Interactions**:
  - none beyond navigation; the totals must stay consistent with the inbox rows

### Settings (`#/settings`)
**Layout**: single form card
**Template classes**: `.card`, `.form-group`, `.form-label`, `.form-input`, `.btn`
**Components**:
  - Auto-approve threshold field, pre-filled "$75.00"
  - Default currency field, pre-filled "USD"
  - Finance contact field, pre-filled "finance@ledgerline.io"
  - Save policy button → shows the inline confirmation "Policy saved."
**Interactions**:
  - Save policy → writes the confirmation line under the button; no navigation

## State & Data Model
expenses: array — five records keyed by id 2201–2205 with merchant, amount, category, submitted, employee, costCentre, method, receiptRef, status
filters: object — { status: "all" } driving the Inbox table
settings: object — { autoApprove: "$75.00", currency: "USD", contact: "finance@ledgerline.io" }

## Navigation Flows
sidebar Inbox → `#/inbox`
sidebar Reports → `#/reports`
sidebar Settings → `#/settings`
inbox row (any) → `#/expense/{that row's id}`
expense detail back link → `#/inbox`

## Design Notes
- Color scheme: neutral slate surfaces; indigo `--accent` for the active nav item and active filter; approval green and rejection red appear only inside status badges and their two action buttons
- Typography: one grotesk sans throughout; `font-variant-numeric: tabular-nums` on every amount column
- Density: compact 10px row padding; the inbox and its filter bar fit without scrolling
</spec>
