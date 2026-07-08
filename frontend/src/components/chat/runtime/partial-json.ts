/**
 * partial-json — tolerant repair + parse of a TRUNCATED JSON prefix (borrow #1).
 *
 * Adapted from nexu-io/open-design (Apache-2.0) — see /THIRD-PARTY-NOTICES.md
 *
 * Clean-room reimplementation (from the behavioral spec, no build-time dep on
 * open-design source) of upstream `runtime/partial-json.ts` lines 16-93
 * (`repairJsonPrefix` / `parsePartialJson`). It powers live streaming previews:
 * a run frame can carry a half-written JSON tool-arg / result blob, and this
 * turns the incomplete prefix into the best-effort object we can render NOW.
 *
 * Design (T-31-01-D — bounded, no unbounded backtracking): a SINGLE forward
 * recursive-descent pass over the input. The scan cursor only ever advances, so
 * the worst case is O(n) with no re-scan. On truncation each open container
 * closes with what it has; `parsePartialJson` returns `undefined` (never throws,
 * never loops) on genuinely un-salvageable input.
 *
 * Truncation policy (the two documented shapes):
 *   - An unterminated string VALUE is closed and KEPT when it is the only /
 *     first element of its container (`{"a":"he` -> `{a:"he"}`).
 *   - An incomplete trailing key/value is DROPPED when its container already
 *     holds a complete element (`{"a":1,"b":"tex` -> `{a:1}`; `[1,2,` -> `[1,2]`).
 *   In both cases the salvage never reduces a container to empty when a partial
 *   value can be kept, and never keeps a partial that shadows real prior data.
 */

interface ParsedValue {
  value: unknown;
  /** false when the value ran into the truncation edge (string/number/nested cut short). */
  complete: boolean;
}

type ParseResult = { ok: true; value: unknown } | { ok: false };

/** Tolerantly parse a (possibly truncated) JSON prefix into a JS value. */
function tolerantParse(input: string): ParseResult {
  if (typeof input !== "string") return { ok: false };
  const s = input;
  const n = s.length;
  let i = 0;

  const skipWs = (): void => {
    while (i < n) {
      const c = s.charCodeAt(i);
      if (c === 32 || c === 9 || c === 10 || c === 13) i++;
      else break;
    }
  };

  const parseString = (): ParsedValue => {
    i++; // consume the opening quote
    let out = "";
    while (i < n) {
      const ch = s[i];
      if (ch === "\\") {
        if (i + 1 >= n) {
          // dangling backslash at the truncation edge — stop, string incomplete
          i = n;
          return { value: out, complete: false };
        }
        const esc = s[i + 1];
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
            const hex = s.slice(i + 2, i + 6);
            if (/^[0-9a-fA-F]{4}$/.test(hex)) {
              out += String.fromCharCode(parseInt(hex, 16));
              i += 6;
              continue;
            }
            // truncated \u escape — stop, incomplete
            i = n;
            return { value: out, complete: false };
          }
          default:
            out += esc;
            break;
        }
        i += 2;
        continue;
      }
      if (ch === '"') {
        i++; // consume the closing quote
        return { value: out, complete: true };
      }
      out += ch;
      i++;
    }
    // ran off the end with no closing quote — close it, mark incomplete
    return { value: out, complete: false };
  };

  const parseNumber = (): ParsedValue => {
    const start = i;
    if (s[i] === "-") i++;
    while (i < n && s[i] >= "0" && s[i] <= "9") i++;
    if (i < n && s[i] === ".") {
      i++;
      while (i < n && s[i] >= "0" && s[i] <= "9") i++;
    }
    if (i < n && (s[i] === "e" || s[i] === "E")) {
      i++;
      if (i < n && (s[i] === "+" || s[i] === "-")) i++;
      while (i < n && s[i] >= "0" && s[i] <= "9") i++;
    }
    const raw = s.slice(start, i);
    const num = Number(raw);
    const finite = Number.isFinite(num);
    // Incomplete when it is a bare sign or dangles on a separator that expects
    // more digits (`-`, `1.`, `2e`, `3e-`).
    const complete = finite && raw !== "-" && !/[.eE][+-]?$/.test(raw);
    return { value: finite ? num : 0, complete };
  };

  // null when the token is neither the full keyword nor a truncation-edge
  // prefix of it (i.e. it is genuine garbage that merely shares a first letter).
  const parseKeyword = (word: string, value: unknown): ParsedValue | null => {
    if (s.startsWith(word, i)) {
      i += word.length;
      return { value, complete: true };
    }
    // a partial keyword at the truncation edge (`tr`, `fals`, `nul`) — only when
    // the remaining input runs to the end (a real truncation, not garbage).
    const rest = s.slice(i);
    if (rest.length > 0 && word.startsWith(rest)) {
      i = n;
      return { value, complete: false };
    }
    return null;
  };

  // null when no value could even be started (unexpected/absent token).
  const parseValue = (): ParsedValue | null => {
    skipWs();
    if (i >= n) return null;
    const c = s[i];
    if (c === "{") return parseObject();
    if (c === "[") return parseArray();
    if (c === '"') return parseString();
    if (c === "-" || (c >= "0" && c <= "9")) return parseNumber();
    if (c === "t") return parseKeyword("true", true);
    if (c === "f") return parseKeyword("false", false);
    if (c === "n") return parseKeyword("null", null);
    return null;
  };

  const parseObject = (): ParsedValue => {
    i++; // consume '{'
    const obj: Record<string, unknown> = {};
    let count = 0;
    for (;;) {
      skipWs();
      if (i >= n) return { value: obj, complete: false };
      if (s[i] === "}") {
        i++;
        return { value: obj, complete: true };
      }
      if (s[i] === ",") {
        i++; // tolerate a dangling / leading comma
        continue;
      }
      if (s[i] !== '"') {
        // an unexpected token where a key belongs — stop with what we have
        return { value: obj, complete: false };
      }
      const keyR = parseString();
      if (!keyR.complete) {
        // truncated key — drop the incomplete pair
        return { value: obj, complete: false };
      }
      const key = keyR.value as string;
      skipWs();
      if (i >= n || s[i] !== ":") {
        // no colon reached — incomplete pair, drop
        return { value: obj, complete: false };
      }
      i++; // consume ':'
      const valR = parseValue();
      if (valR === null) {
        // truncated right after the colon — drop the pair
        return { value: obj, complete: false };
      }
      if (!valR.complete) {
        // salvage a partial value only when it would not shadow prior data
        if (count === 0) obj[key] = valR.value;
        return { value: obj, complete: false };
      }
      obj[key] = valR.value;
      count++;
    }
  };

  const parseArray = (): ParsedValue => {
    i++; // consume '['
    const arr: unknown[] = [];
    for (;;) {
      skipWs();
      if (i >= n) return { value: arr, complete: false };
      if (s[i] === "]") {
        i++;
        return { value: arr, complete: true };
      }
      if (s[i] === ",") {
        i++; // tolerate a dangling / leading comma
        continue;
      }
      const valR = parseValue();
      if (valR === null) return { value: arr, complete: false };
      if (!valR.complete) {
        if (arr.length === 0) arr.push(valR.value);
        return { value: arr, complete: false };
      }
      arr.push(valR.value);
    }
  };

  skipWs();
  const top = parseValue();
  if (top === null) return { ok: false };
  return { ok: true, value: top.value };
}

/**
 * Repair a (possibly truncated) JSON prefix into a valid, canonical JSON string.
 * Returns `""` when nothing could be salvaged.
 */
export function repairJsonPrefix(prefix: string): string {
  const r = tolerantParse(prefix);
  return r.ok ? JSON.stringify(r.value) : "";
}

/**
 * Parse a (possibly truncated) JSON prefix into a value. Returns `undefined`
 * on empty / garbage / un-salvageable input — never throws.
 */
export function parsePartialJson<T = unknown>(prefix: string): T | undefined {
  const r = tolerantParse(prefix);
  return r.ok ? (r.value as T) : undefined;
}
