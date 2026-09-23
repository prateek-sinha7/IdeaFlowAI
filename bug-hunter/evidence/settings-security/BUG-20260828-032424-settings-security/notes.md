## Source correlation

`backend/app/api/auth.py` GET /mfa docstring (line ~912):
"Returns 200 with `supported=false` for a non-Cognito (break-glass) account"

`frontend/src/components/settings/SecuritySection.tsx` lines 231-240 — the component's own
code comment says the correct reason:
  // A break-glass/local account has no Cognito factors to manage. Say so
  // plainly instead of rendering controls that would 501.
...but the copy actually shown to the user does NOT say that. It says:
  "This account's credentials are managed outside the application, so
   two-factor authentication is configured separately."

That copy is the message written for a Cognito-backed account (credentials genuinely held by
an external IdP). It is reused verbatim for break-glass/local accounts, where it is false:
`backend/app/api/auth.py` POST /change-password (auth_provider == "local" branch, line ~1254)
verifies the CURRENT password against `user.password_hash` (bcrypt, in this app's own DB) and
writes the new hash back into this app's own DB. The Profile tab's own "Change Password" form
(Current password / New password / Confirm new password / Change Password button) is the proof
this app is the credential store for this account -- nothing is "managed outside the
application."
