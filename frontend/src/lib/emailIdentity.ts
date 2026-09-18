/** Normalize the case-insensitive email identifier sent to authentication APIs. */
export function canonicalizeEmail(email: string): string {
  return email.trim().toLowerCase();
}
