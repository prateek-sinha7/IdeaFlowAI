/**
 * Canonical manifest form (design section 3.10.8) [pending G-34].
 *
 * Port of `backend/app/agents/workflow_builder/canonical.py`. The two modules
 * must agree; `canonicalManifest.cases.json` pins that (parity tests: task 18.6).
 *
 * Normalisation, applied to every step (top level and `subagents.steps`):
 *
 * 1. Drop keys whose value is `null`, at any depth. List items are kept.
 * 2. Remove keys that equal the composer default: `tools.exec: false`,
 *    `tools.read_files: true`, `tools.write_files: true`, `gates: []` and
 *    `depends_on` when it equals the sequential order the canvas derives.
 *    A `tools` object that is empty after this removal is removed too.
 *    Apply-and-save also writes three keys that carry no information, so they
 *    are defaults as well: `name` on a custom step when it equals the step's
 *    `instance_id`, `strategy: "single_shot"` on a leaf step (one with no
 *    `subagents` key) and `tools.spawn_subagents: false` on a parent step (one
 *    with a `subagents` key). A `name` that differs from the instance id, any
 *    other strategy and `spawn_subagents: true` are kept.
 * 3. Serialise with keys sorted by Unicode code point, compact separators and
 *    no ASCII escaping.
 *
 * List order is never changed.
 *
 * API choice: `canonicalHash` is async. SHA-256 comes from
 * `globalThis.crypto.subtle.digest`, which exists in browsers (secure contexts)
 * and in Node/Vitest, and is async by specification. `canonicalize` and
 * `canonicalJson` are synchronous and pure. Hashing needs a secure context
 * (https or localhost); without one `canonicalHash` rejects with a clear error.
 *
 * Known limits against Python (JSON numbers only):
 * - JavaScript cannot tell `1.0` from `1`, so an integral float is written
 *   `1` here and `1.0` in Python. Manifests do not use such floats.
 * - Exponent formatting of very large or very small floats differs.
 * - A lone surrogate in a string is escaped here; Python fails to encode it.
 */

/** A JSON value as parsed from a manifest. */
export type JsonValue =
  | null
  | boolean
  | number
  | string
  | JsonValue[]
  | { [key: string]: JsonValue };

/** A JSON object. */
export type JsonObject = { [key: string]: JsonValue };

const CUSTOM_AGENT_PREFIX = "custom-agent:";

const TOOL_DEFAULTS: Readonly<Record<string, boolean>> = {
  exec: false,
  read_files: true,
  write_files: true,
};

/** Defaults that only apply to a parent step (one that has `subagents`). */
const PARENT_TOOL_DEFAULTS: Readonly<Record<string, boolean>> = {
  spawn_subagents: false,
};

const LEAF_DEFAULT_STRATEGY = "single_shot";

type Unknown = Readonly<Record<string, unknown>>;

function isMapping(value: unknown): value is Unknown {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Own entries without prototype lookups; `__proto__` stays a plain key. */
function entriesOf(value: Unknown): [string, unknown][] {
  return Object.entries(value);
}

function fromEntries(entries: readonly (readonly [string, unknown])[]): Record<string, unknown> {
  // Object.fromEntries defines own properties, so a "__proto__" key is safe.
  return Object.fromEntries(entries);
}

/**
 * Return the canonical form of `manifest` as a new plain object.
 *
 * The input is not modified. Nulls are dropped first, so a `tools` object
 * holding only defaults and nulls is judged empty and removed.
 */
export function canonicalize(manifest: Readonly<Record<string, unknown>>): JsonObject {
  const cleaned = dropNulls(manifest);
  return stripManifestDefaults(cleaned as Unknown) as JsonObject;
}

/**
 * Serialise the canonical form of `manifest`: keys sorted by code point,
 * separators `,` and `:`, non-ASCII written as is.
 *
 * @throws Error when the manifest holds NaN, an infinity or an unsupported type.
 */
export function canonicalJson(manifest: Readonly<Record<string, unknown>>): string {
  return serialise(canonicalize(manifest));
}

/**
 * SHA-256 of the canonical JSON (UTF-8) as 64 lowercase hex digits, no prefix.
 *
 * Two manifests that differ only by the documented composer defaults, by
 * `null` values or by key order have the same hash.
 */
export async function canonicalHash(manifest: Readonly<Record<string, unknown>>): Promise<string> {
  const subtle = globalThis.crypto?.subtle;
  if (!subtle) {
    throw new Error("canonicalHash needs crypto.subtle (a secure context: https or localhost)");
  }
  const bytes = new TextEncoder().encode(canonicalJson(manifest));
  const digest = await subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function stripManifestDefaults(manifest: Unknown): Record<string, unknown> {
  const result = fromEntries(entriesOf(manifest));
  const steps = result["steps"];
  if (Array.isArray(steps)) {
    result["steps"] = stripSteps(steps, true);
  }
  return result;
}

function stripSteps(steps: readonly unknown[], topLevel: boolean): unknown[] {
  const routeTargets = topLevel ? routeTargetIds(steps) : new Set<string>();
  return steps.map((step, index) => {
    if (!isMapping(step)) {
      return step;
    }
    const previous = topLevel && index > 0 ? steps[index - 1] : null;
    return stripStep(step, sequentialDependsOn(step, previous, routeTargets));
  });
}

function stripStep(step: Unknown, expectedDependsOn: readonly string[]): Record<string, unknown> {
  const result = fromEntries(entriesOf(step));
  const isParent = Object.hasOwn(result, "subagents");

  const instanceId = result["instance_id"];
  if (typeof instanceId === "string" && instanceId !== "" && result["name"] === instanceId) {
    delete result["name"];
  }

  if (!isParent && result["strategy"] === LEAF_DEFAULT_STRATEGY) {
    delete result["strategy"];
  }

  const tools = result["tools"];
  if (isMapping(tools)) {
    const defaults = isParent ? { ...TOOL_DEFAULTS, ...PARENT_TOOL_DEFAULTS } : TOOL_DEFAULTS;
    const kept = entriesOf(tools).filter(
      ([key, value]) => !(Object.hasOwn(defaults, key) && value === defaults[key]),
    );
    if (kept.length > 0) {
      result["tools"] = fromEntries(kept);
    } else {
      delete result["tools"];
    }
  }

  const gates = result["gates"];
  if (Array.isArray(gates) && gates.length === 0) {
    delete result["gates"];
  }

  const dependsOn = result["depends_on"];
  if (
    Array.isArray(dependsOn) &&
    dependsOn.length === expectedDependsOn.length &&
    dependsOn.every((item, index) => item === expectedDependsOn[index])
  ) {
    delete result["depends_on"];
  }

  const subagents = result["subagents"];
  if (isMapping(subagents)) {
    const inner = subagents["steps"];
    if (Array.isArray(inner)) {
      result["subagents"] = { ...subagents, steps: stripSteps(inner, false) };
    }
  }
  return result;
}

/** Backend agent id of a step, as the composer derives it. */
function stepAgentId(step: unknown): string {
  if (!isMapping(step)) {
    return "";
  }
  const instanceId = step["instance_id"];
  if (typeof instanceId === "string" && instanceId !== "") {
    return `${CUSTOM_AGENT_PREFIX}${instanceId}`;
  }
  const agent = step["agent"];
  return typeof agent === "string" ? agent : "";
}

/** Targets of every `route.outcomes` entry whose trigger is `step`. */
function routeTargetIds(steps: readonly unknown[]): ReadonlySet<string> {
  const targets = new Set<string>();
  for (const step of steps) {
    if (!isMapping(step)) {
      continue;
    }
    const route = step["route"];
    const outcomes = isMapping(route) ? route["outcomes"] : null;
    if (!isMapping(outcomes)) {
      continue;
    }
    for (const outcome of Object.values(outcomes)) {
      if (!isMapping(outcome)) {
        continue;
      }
      const target = outcome["target"];
      if (outcome["trigger"] === "step" && typeof target === "string" && target !== "") {
        targets.add(target);
      }
    }
  }
  return targets;
}

/**
 * The `depends_on` list the composer canvas derives for `step`: the ids of its
 * own sub-agents first, then the previous top-level step unless this step is
 * the first or the target of a `step` route. `previous` is `null` for the first
 * top-level step and for every nested step (a `null` list item counts as none,
 * as in Python).
 */
function sequentialDependsOn(
  step: Unknown,
  previous: unknown,
  routeTargets: ReadonlySet<string>,
): string[] {
  const expected: string[] = [];

  const subagents = step["subagents"];
  if (isMapping(subagents)) {
    const inner = subagents["steps"];
    if (Array.isArray(inner)) {
      for (const child of inner) {
        const childId = stepAgentId(child);
        if (childId !== "") {
          expected.push(childId);
        }
      }
    }
  }

  if (previous !== null && previous !== undefined) {
    const ownId = stepAgentId(step);
    const instanceId = step["instance_id"];
    const isRouteTarget =
      routeTargets.has(ownId) ||
      (typeof instanceId === "string" && instanceId !== "" && routeTargets.has(instanceId));
    const previousId = stepAgentId(previous);
    if (!isRouteTarget && previousId !== "") {
      expected.push(previousId);
    }
  }
  return expected;
}

/** Copy `value` without `null` (or `undefined`) object values, at any depth. */
function dropNulls(value: unknown): unknown {
  if (isMapping(value)) {
    return fromEntries(
      entriesOf(value)
        .filter(([, item]) => item !== null && item !== undefined)
        .map(([key, item]) => [key, dropNulls(item)] as const),
    );
  }
  if (Array.isArray(value)) {
    return value.map(dropNulls);
  }
  return value;
}

/** Compare strings by Unicode code point, like Python's `sort_keys`. */
function compareCodePoints(a: string, b: string): number {
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    const ca = a.codePointAt(i) as number;
    const cb = b.codePointAt(j) as number;
    if (ca !== cb) {
      return ca - cb;
    }
    i += ca > 0xffff ? 2 : 1;
    j += cb > 0xffff ? 2 : 1;
  }
  return a.length - i - (b.length - j);
}

function serialise(value: unknown): string {
  if (value === null) {
    return "null";
  }
  switch (typeof value) {
    case "boolean":
      return value ? "true" : "false";
    case "number":
      if (!Number.isFinite(value)) {
        throw new Error("Out of range float values are not JSON compliant");
      }
      return JSON.stringify(value);
    case "string":
      return JSON.stringify(value);
    default:
      break;
  }
  if (Array.isArray(value)) {
    return `[${value.map(serialise).join(",")}]`;
  }
  if (isMapping(value)) {
    const parts = entriesOf(value)
      .sort(([a], [b]) => compareCodePoints(a, b))
      .map(([key, item]) => `${JSON.stringify(key)}:${serialise(item)}`);
    return `{${parts.join(",")}}`;
  }
  throw new TypeError(`Object of type ${typeof value} is not JSON serializable`);
}
