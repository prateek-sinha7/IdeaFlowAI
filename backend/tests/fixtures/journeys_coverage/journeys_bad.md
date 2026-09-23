# Chroma Quote Workbench: Navigable Prototype Build Specification

## STAGE 1: CRIMSON MODULE

### JOURNEY: New Quote Initiation
**Stage:** Crimson (Screens 1–2)  
**Description:** Establishes client identity and policy context, then captures coverage preferences.

---

## SCREEN 1: ANCHOR

**Product:** Chroma Quote Workbench — Module: Crimson  
**Purpose:** Starts a new insurance quote by capturing the client and policy basics.

**FIELDS**

| Label | Type | Mandatory | Default | Options |
|-------|------|-----------|---------|---------|
| Client Name | text | Yes | | |
| Policy Type | dropdown | Yes | | Auto, Home, Renters, Umbrella |
| Effective Date | date | Yes | | |
| Notes | textarea | No | | |

**BUTTONS**

| Caption | Action | Navigates To |
|---------|--------|--------------|
| Begin Quote | Proceed to coverage selection | Screen 2: Beacon |
| Cancel | Reset all fields on this screen | Screen 1: Anchor |

**TAGLINE**

"An anchor is only useful when you know the depth."  
Styling: bold  
Colour: #942222

**VALIDATION**

- Client Name is mandatory and must be provided.
- Policy Type is mandatory; user must select exactly one option.
- Effective Date is mandatory and cannot be in the past.
- Notes is optional.
- Begin Quote button is disabled until all mandatory fields are completed.

**SOURCE:** doc-1.md (1-crimson.pdf)

---

## SCREEN 2: BEACON

**Product:** Chroma Quote Workbench — Module: Crimson  
**Purpose:** Confirms the coverage limits and optional add-ons for the quote.

**FIELDS**

| Label | Type | Mandatory | Default | Options |
|-------|------|-----------|---------|---------|
| Liability Limit | dropdown | Yes | | $50,000, $100,000, $300,000, $500,000 |
| Deductible | dropdown | Yes | | $250, $500, $1,000 |
| Add Roadside Assistance | checkbox | No | unchecked | |
| Add Rental Reimbursement | checkbox | No | unchecked | |

**BUTTONS**

| Caption | Action | Navigates To |
|---------|--------|--------------|
| Back | Return to previous screen | Screen 1: Anchor |
| Continue | Proceed to applicant details | Screen 3: Kindle |

**TAGLINE**

"A beacon does not move; it simply refuses to go out."  
Styling: italic  
Colour: #943022

**VALIDATION**

- Liability Limit is mandatory; user must select exactly one option.
- Deductible is mandatory; user must select exactly one option.
- Deductible must be lower than the selected Liability Limit band (numeric comparison).
- Add Roadside Assistance and Add Rental Reimbursement are optional.
- Continue button is disabled until both mandatory fields are completed and validation passes.

**SOURCE:** doc-1.md (1-crimson.pdf)

---

## STAGE 2: AMBER MODULE

### JOURNEY: Applicant and Asset Underwriting
**Stage:** Amber (Screens 3–4)  
**Description:** Captures applicant demographics and asset details for underwriting.

---

## SCREEN 3: KINDLE

**Product:** Chroma Quote Workbench — Module: Amber  
**Purpose:** Captures the applicant's personal details for underwriting.

**FIELDS**

| Label | Type | Mandatory | Default | Options |
|-------|------|-----------|---------|---------|
| Date of Birth | date | Yes | | |
| Marital Status | dropdown | Yes | | Single, Married, Divorced, Widowed |
| Prior Insurance Carrier | text | No | | |
| Years Licensed | text | Yes | | |

**BUTTONS**

| Caption | Action | Navigates To |
|---------|--------|--------------|
| Back | Return to coverage selection | Screen 2: Beacon |
| Next | Proceed to asset details | Screen 4: Lantern |

**TAGLINE**

"YOU CANNOT KINDLE WHAT YOU WILL NOT GATHER."  
Styling: uppercase  
Colour: #7D9422

**VALIDATION**

- Date of Birth is mandatory.
- Marital Status is mandatory; user must select exactly one option.
- Prior Insurance Carrier is optional.
- Years Licensed is mandatory and must be numeric.

**SOURCE:** doc-2.md (2-amber.docx)

---

## SCREEN 4: LANTERN

**Product:** Chroma Quote Workbench — Module: Amber  
**Purpose:** Records the vehicle or property being insured.

**FIELDS**

| Label | Type | Mandatory | Default | Options |
|-------|------|-----------|---------|---------|
| Asset Type | radio | Yes | | Vehicle, Property |
| Year | text | Yes | | |
| Make/Model | text | Yes | | |
| Safety Features | checkbox | No | | Anti-lock Brakes, Alarm, Sprinkler System |

**BUTTONS**

| Caption | Action | Navigates To |
|---------|--------|--------------|
| Back | Return to applicant details | Screen 3: Kindle |
| Next | Proceed to claims questionnaire | Screen 5: Umbra |

**TAGLINE**

"A LANTERN LIGHTS THE STEP, NOT THE JOURNEY."  
Styling: small caps  
Colour: #709422

**VALIDATION**

- Asset Type is mandatory; user must select either Vehicle or Property.
- Year is mandatory and must be between 1980 and the current year.
- Make/Model is mandatory.
- Safety Features is optional; user may select zero or more checkboxes.

**SOURCE:** doc-2.md (2-amber.docx)

---

## STAGE 3: VERDANT MODULE

### JOURNEY: Risk Assessment and Discount Selection
**Stage:** Verdant (Screens 5–6)  
**Description:** Evaluates claims history and presents available discounts.

---

## SCREEN 5: MISSING

This screen was not found in the notes provided during this pass.

---

## SCREEN 6: MISSING

This screen was not found in the notes provided during this pass.

---

## SCREEN 7: MISSING

This screen was not found in the notes provided during this pass.

---

## SCREEN 8: MISSING

This screen was not found in the notes provided during this pass.

---
## STAGE 5: VIOLET MODULE

### JOURNEY: Payment Collection and Confirmation
**Stage:** Violet (Screens 9–10)  
**Description:** Collects payment details, processes transaction, and delivers purchase confirmation.

---

## SCREEN 9: PLINTH

**Product:** Chroma Quote Workbench — Module: Violet  
**Purpose:** Collects payment details to finalise the quote purchase.

**FIELDS**

| Label | Type | Mandatory | Default | Options |
|-------|------|-----------|---------|---------|
| Card Number | text | Yes | | |
| Expiration Date | date | Yes | | |
| CVV | text | Yes | | |
| Billing Zip | text | Yes | | |

**BUTTONS**

| Caption | Action | Navigates To |
|---------|--------|--------------|
| Back | Return to signature review | Screen 8: Gossamer |
| Pay Now | Process payment and confirm purchase | Screen 10: Quill |

**TAGLINE**

"A plinth makes the ordinary deliberate."  
Styling: strikethrough  
Colour: #7D2294

**VALIDATION**

- Card Number is mandatory and must be exactly 16 digits.
- Expiration Date is mandatory.
- CVV is mandatory and must be exactly 3 digits.
- Billing Zip is mandatory.
- Pay Now button is disabled until all mandatory fields are completed and validation passes.

**SOURCE:** doc-5.md (5-violet.pdf)

---

## SCREEN 10: QUILL

**Product:** Chroma Quote Workbench — Module: Violet  
**Purpose:** Confirms the purchase and offers a copy of the confirmation.

**FIELDS**

| Label | Type | Mandatory | Default | Options |
|-------|------|-----------|---------|---------|
| Email Confirmation Copy To | text | No | | |

**BUTTONS**

| Caption | Action | Navigates To |
|---------|--------|--------------|
| Download PDF | Download confirmation PDF | Screen 10: Quill (self-navigation) |
| Return to Dashboard | Exit to main dashboard | Screen 1: Anchor |

**TAGLINE**

"A quill spends ink it cannot recall."  
Styling: oblique  
Colour: #8B2294

**VALIDATION**

- Email Confirmation Copy To is optional.
- If provided, Email Confirmation Copy To must be in valid email format (user@domain.com).
- Email validation only applies if the field is populated.

**SOURCE:** doc-5.md (5-violet.pdf)

---

## END OF BUILD SPECIFICATION

