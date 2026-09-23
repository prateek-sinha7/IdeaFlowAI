# Document 4: 4-azure.xlsx

## PURPOSE
This spreadsheet documents two screens (7: Furrow and 8: Gossamer) in the Azure module of the Chroma Quote Workbench. Screen 7 presents the calculated premium and payment cadence options to the user, while Screen 8 requires final review, e-signature, and agreement to terms before submission.

## SCREENS

### Screen 7: Furrow

**Title:** Screen 7: Furrow

**Product:** Chroma Quote Workbench — Module: Azure

**Description:** Summarises the calculated premium and payment cadence.

**Fields:**
- Payment Plan (dropdown, mandatory): Options are Monthly, Quarterly, Semi-Annual, Annual, Paid in Full
- Auto-pay Enrollment (checkbox, not mandatory)

**Buttons:**
- Back → Screen 6: Vellum
- Next → Screen 8: Gossamer

**Quote Text:** "A f u r r o w i s a d e c i s i o n t h e f i e l d m u s t k e e p ."

**Styling:** letter-spaced, colour: #225094

---

### Screen 8: Gossamer

**Title:** Screen 8: Gossamer

**Product:** Chroma Quote Workbench — Module: Azure

**Description:** Final review and e-signature before the quote is submitted.

**Fields:**
- E-Signature (text, mandatory)
- Signature Date (date, mandatory, defaults to today)
- I agree to Terms (checkbox, mandatory)

**Buttons:**
- Back → Screen 7: Furrow
- Submit Quote → Screen 9: Plinth

**Quote Text:** "Gossamer holds because it does not resist."

**Styling:** bold italic, colour: #224294

## FLOW

1. User arrives at Screen 7: Furrow after completing discounts selection on Screen 6: Vellum
2. User selects a payment plan from dropdown options (Monthly, Quarterly, Semi-Annual, Annual, or Paid in Full)
3. User optionally enrolls in auto-pay by checking the Auto-pay Enrollment checkbox
4. User clicks Next to proceed to Screen 8: Gossamer
5. On Screen 8, user enters their e-signature (must match Client Name from Screen 1)
6. User reviews the signature date (automatically populated with today's date, but can be modified)
7. User confirms agreement to terms by checking the "I agree to Terms" checkbox
8. User clicks Submit Quote to proceed to Screen 9: Plinth (payment details)
9. Alternatively, user can click Back at any point to return to the previous screen

## DATA

**Screen 7: Furrow**
- Reads: None (initial screen values)
- Writes: 
  - Payment Plan (selected value from dropdown)
  - Auto-pay Enrollment (boolean checkbox state)

**Screen 8: Gossamer**
- Reads:
  - Client Name (from Screen 1: Anchor) — used for validation
- Writes:
  - E-Signature (text entry)
  - Signature Date (date, defaults to today)
  - I agree to Terms (boolean checkbox state)

## RULES

**Screen 7: Furrow Validation:**
- None specified.

**Screen 7: Furrow Field Rules:**
- Payment Plan is mandatory; user must select one of: Monthly, Quarterly, Semi-Annual, Annual, or Paid in Full
- Auto-pay Enrollment is optional

**Screen 8: Gossamer Validation:**
- E-Signature must match the Client Name from Screen 1 (exact match required)
- Terms checkbox is mandatory (must be checked to proceed)

**Screen 8: Gossamer Field Rules:**
- E-Signature is mandatory
- Signature Date is mandatory and defaults to today's date (but user can modify it)
- I agree to Terms is mandatory (checkbox must be checked)

**Navigation Rules:**
- Screen 7 Back button returns to Screen 6: Vellum
- Screen 7 Next button proceeds to Screen 8: Gossamer
- Screen 8 Back button returns to Screen 7: Furrow
- Screen 8 Submit Quote button proceeds to Screen 9: Plinth

## UNCERTAIN

- The document does not specify what happens if the e-signature does not match the client name — is there an error message, or is the submission simply blocked?
- The document does not clarify whether the Signature Date is editable by the user or read-only with today's date auto-filled.
- Payment Plan options and their effect on the quote/billing are not detailed — the document lists the dropdown values but not their business meaning or impact.
- The document does not specify what happens after "Submit Quote" — does the user immediately proceed to Screen 9: Plinth, or is there a confirmation step?
- The document does not provide information about Auto-pay Enrollment behavior — whether selecting it pre-fills any information on later screens or affects payment processing.
- No information is provided about the styling of the quote text (letter-spaced and bold italic) or whether this is decorative or functional.
