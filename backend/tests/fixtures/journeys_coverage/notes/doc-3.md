# Document 3: 3-verdant.pptx

## PURPOSE
This document describes two screens in the Verdant module of the Chroma Quote Workbench: Screen 5 (Umbra) runs a risk questionnaire covering claims history, and Screen 6 (Vellum) presents available discounts for selection before premium calculation. Both screens are part of the mid-workflow underwriting and discount capture phase.

## SCREENS

### Screen 5: Umbra
Product: Chroma Quote Workbench — Module: Verdant

Runs a short risk questionnaire covering claims history.

**Fields:**
- Prior Claims in Last 5 Years (radio button) — Mandatory — Options: Yes, No
- Claims Count (text) — Conditional
- Credit-Based Insurance Consent (checkbox) — Mandatory

**Buttons:**
- Back → Screen 4: Lantern
- Next → Screen 6: Vellum

**Quote/Motto:** "Umbra is not absence; it is proof of light."
- Styling: monospace
- Colour: #229450

### Screen 6: Vellum
Product: Chroma Quote Workbench — Module: Verdant

Offers available discounts before premium calculation.

**Fields:**
- Bundle with Home Policy (checkbox) — Not mandatory
- Paperless Billing (checkbox) — Not mandatory
- Good Student Discount (checkbox) — Not mandatory

**Buttons:**
- Back → Screen 5: Umbra
- Next → Screen 7: Furrow

**Quote/Motto:** "Vellum keeps what paper forgets."
- Styling: underlined
- Colour: #22945E

## FLOW
1. User arrives at Screen 5: Umbra after completing Screen 4: Lantern (property/vehicle details).
2. User selects Prior Claims status (Yes or No).
3. If Prior Claims = Yes, user enters Claims Count.
4. User selects Credit-Based Insurance Consent checkbox status.
5. User clicks Next to proceed to Screen 6: Vellum.
6. User selects any applicable discounts (Bundle with Home Policy, Paperless Billing, Good Student Discount).
7. User clicks Next to proceed to Screen 7: Furrow.

Alternative: User clicks Back on either screen to return to the previous screen.

## DATA

**Screen 5: Umbra reads/writes:**
- Prior Claims in Last 5 Years (radio: Yes / No)
- Claims Count (text, conditional)
- Credit-Based Insurance Consent (checkbox state)

**Screen 6: Vellum reads/writes:**
- Bundle with Home Policy (checkbox state)
- Paperless Billing (checkbox state)
- Good Student Discount (checkbox state)

## RULES
- Claims Count is mandatory only when Prior Claims = Yes. If Prior Claims = No, Claims Count is disabled or not displayed.
- Credit-Based Insurance Consent is a mandatory field on Screen 5.
- All discount checkboxes on Screen 6 are optional (not mandatory).
- Screen 6 has no validation rules beyond field optionality.
- Navigation: Back button from Screen 6 returns to Screen 5; Back button from Screen 5 returns to Screen 4.
- Navigation: Next button from Screen 5 advances to Screen 6; Next button from Screen 6 advances to Screen 7.

## UNCERTAIN
- The specific label or placeholder text for the Credit-Based Insurance Consent checkbox on Screen 5 is not fully legible in the extracted text due to OCR artifacts ("BInusttuorannsc: eB aSccok r-e").
- The exact label wording for the discount checkboxes on Screen 6 is partially corrupted ("BMuuttltio-ncsa: B Daicskc o->u nStcreench").
- The data persistence mechanism (session, database, etc.) is not specified.
- Whether Prior Claims = Yes/No triggers a backend service or purely client-side conditional logic is not stated.
- The destination and purpose of Screen 7: Furrow are not documented here.
