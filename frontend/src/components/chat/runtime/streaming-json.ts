/**
 * streaming-json — pull a single named string field out of an OPEN JSON
 * fragment (borrow #2).
 *
 * Adapted from nexu-io/open-design (Apache-2.0) — see /THIRD-PARTY-NOTICES.md
 *
 * Clean-room reimplementation (from the behavioral spec, no build-time dep on
 * open-design source) of the upstream single-field streaming extractor at
 * `AssistantMessage.tsx:2786`. While a JSON tool-arg blob is still streaming in,
 * we often want to show ONE field live (e.g. the `content` being written or the
 * target `path`) before the whole object is closeable. This scans the fragment
 * for `"<field>": "<value…`, decodes JSON escapes, and returns whatever of the
 * value has arrived so far — tolerant of the value (and the object) being cut
 * off mid-stream.
 *
 * Single forward scan, no backtracking (T-31-01-D): the cursor only advances.
 */

const WS = /\s/;

/**
 * Extract the string value of `field` from a (possibly truncated) JSON
 * `fragment`. Returns the partial value when the stream is cut mid-string, or
 * `undefined` when the field is absent / not a string.
 */
export function extractStreamingJsonString(
  fragment: string,
  field: string,
): string | undefined {
  if (!fragment || !field) return undefined;

  // The exact quoted key token, JSON-escaped so a field with special chars still
  // matches the on-the-wire key spelling.
  const keyToken = JSON.stringify(field);
  const len = fragment.length;

  let searchFrom = 0;
  for (;;) {
    const keyIdx = fragment.indexOf(keyToken, searchFrom);
    if (keyIdx === -1) return undefined;

    // Advance the fallback search cursor past this candidate up-front so every
    // `continue` below makes forward progress (no re-scan of the same key).
    searchFrom = keyIdx + keyToken.length;

    let j = keyIdx + keyToken.length;
    while (j < len && WS.test(fragment[j])) j++;
    if (fragment[j] !== ":") continue; // a value-position or substring match — keep looking
    j++;
    while (j < len && WS.test(fragment[j])) j++;
    if (fragment[j] !== '"') continue; // value is not a string (or not arrived yet)
    j++; // step over the opening quote of the value

    let out = "";
    while (j < len) {
      const ch = fragment[j];
      if (ch === "\\") {
        if (j + 1 >= len) return out; // dangling escape at the truncation edge
        const esc = fragment[j + 1];
        switch (esc) {
          case '"':
            out += '"';
            break;
          case "\\":
            out += "\\";
            break;
          case "/":
            out += "/";
            break;
          case "b":
            out += "\b";
            break;
          case "f":
            out += "\f";
            break;
          case "n":
            out += "\n";
            break;
          case "r":
            out += "\r";
            break;
          case "t":
            out += "\t";
            break;
          case "u": {
            const hex = fragment.slice(j + 2, j + 6);
            if (/^[0-9a-fA-F]{4}$/.test(hex)) {
              out += String.fromCharCode(parseInt(hex, 16));
              j += 6;
              continue;
            }
            return out; // truncated \u escape
          }
          default:
            out += esc;
            break;
        }
        j += 2;
        continue;
      }
      if (ch === '"') return out; // closing quote — value complete
      out += ch;
      j++;
    }
    return out; // stream cut mid-value — return what arrived
  }
}
