import fc from "fast-check";
import { describe, expect, it } from "vitest";

import { effortLabel } from "@/components/workflow/AgentsPopup";
import type { CapabilityModelEntry } from "@/lib/api";

import { changeModel, preselect, thinkingOptions } from "./modelPicker";

// Feature: ai-workflow-builder, Property 37: Picker selection
// **Validates: Requirements 6.3, 6.4, 6.6, 6.8**

// Fixed seed keeps failures reproducible.
const PROPERTY_OPTIONS = { seed: 20260512, numRuns: 200 } as const;

const MODEL_POOL = ["m0", "m1", "m2", "m3", "m4", "m5"] as const;
const LEVEL_POOL = ["none", "low", "medium", "high", "xhigh"] as const;
const MODES = ["effort", "adaptive", "budget", "none"] as const;
/** An id that is never offered, to cover a stored or preferred model that is gone. */
const GONE_ID = "gone";

interface Catalog {
  models: CapabilityModelEntry[];
  default_model_id: string;
  default_efforts: Record<string, string | null>;
}

function entry(
  id: string,
  mode: (typeof MODES)[number],
  levels: string[],
): CapabilityModelEntry {
  return {
    id,
    label: id,
    description: "",
    tier: "standard",
    cost_class: "standard",
    provider: "anthropic",
    context_window: 200000,
    user_allowed: true,
    reasoning_mode: mode,
    reasoning_levels: levels,
  };
}

/** The levels the Thinking select may offer: none for `reasoning_mode: none`. */
function expectedLevels(model: CapabilityModelEntry): string[] {
  return model.reasoning_mode === "none" ? [] : (model.reasoning_levels ?? []);
}

/** A model with a mode and a subset of the level pool (kept even for mode none). */
const modelSpec = fc.record({
  mode: fc.constantFrom(...MODES),
  levels: fc.uniqueArray(fc.constantFrom(...LEVEL_POOL), { maxLength: LEVEL_POOL.length }),
});

/** An index into the model's offered levels, used to draw its default effort. */
const defaultPick = fc.nat({ max: LEVEL_POOL.length - 1 });

const catalog: fc.Arbitrary<Catalog> = fc
  .record({
    ids: fc.uniqueArray(fc.constantFrom(...MODEL_POOL), { maxLength: MODEL_POOL.length }),
    specs: fc.array(modelSpec, { minLength: MODEL_POOL.length, maxLength: MODEL_POOL.length }),
    picks: fc.array(defaultPick, {
      minLength: MODEL_POOL.length,
      maxLength: MODEL_POOL.length,
    }),
    defaultModelId: fc.constantFrom<string>(...MODEL_POOL, GONE_ID),
  })
  .map(({ ids, specs, picks, defaultModelId }) => {
    const models = ids.map((id, i) => entry(id, specs[i].mode, specs[i].levels));
    const default_efforts: Record<string, string | null> = {};
    models.forEach((model, i) => {
      const levels = expectedLevels(model);
      default_efforts[model.id] = levels.length === 0 ? null : levels[picks[i] % levels.length];
    });
    return { models, default_model_id: defaultModelId, default_efforts };
  });

const optionalId = fc.constantFrom<string | null>(...MODEL_POOL, GONE_ID, null);
const optionalEffort = fc.constantFrom<string | null>(...LEVEL_POOL, null);

describe("Property 37: Picker selection", () => {
  it("offers the selected model's levels labelled by effortLabel, none without levels", () => {
    fc.assert(
      fc.property(catalog, fc.constantFrom<string>(...MODEL_POOL, GONE_ID), (c, modelId) => {
        const model = c.models.find((m) => m.id === modelId);
        const levels = model ? expectedLevels(model) : [];

        const options = thinkingOptions(modelId, c.models);

        expect(options).toEqual(
          levels.map((value) => ({ value, label: effortLabel(value, model?.reasoning_mode) })),
        );
      }),
      PROPERTY_OPTIONS,
    );
  });

  it("keeps the effort on a model change only when the new model accepts it", () => {
    fc.assert(
      fc.property(
        catalog.filter((c) => c.models.length > 0),
        fc.nat(),
        optionalEffort,
        (c, index, currentEffort) => {
          const next = c.models[index % c.models.length];
          const levels = expectedLevels(next);

          const choice = changeModel(next.id, currentEffort, c);

          expect(choice.modelId).toBe(next.id);
          if (levels.length === 0) {
            expect(choice.effort).toBeNull();
          } else if (currentEffort !== null && levels.includes(currentEffort)) {
            expect(choice.effort).toBe(currentEffort);
          } else {
            expect(choice.effort).toBe(c.default_efforts[next.id]);
          }
        },
      ),
      PROPERTY_OPTIONS,
    );
  });

  it("preselects the stored model, else the preference, else the default model", () => {
    fc.assert(
      fc.property(
        catalog,
        optionalId,
        optionalEffort,
        optionalId,
        (c, storedId, storedEffort, preferredId) => {
          const offered = new Set(c.models.map((m) => m.id));
          const isOffered = (id: string | null): id is string => id !== null && offered.has(id);

          const { choice } = preselect({
            response: c,
            stored: storedId === null ? null : { modelId: storedId, effort: storedEffort },
            preferredModelId: preferredId,
          });

          if (c.models.length === 0) {
            expect(choice).toBeNull();
            return;
          }
          const expectedId = isOffered(storedId)
            ? storedId
            : isOffered(preferredId)
              ? preferredId
              : offered.has(c.default_model_id)
                ? c.default_model_id
                : c.models[0].id;
          const model = c.models.find((m) => m.id === expectedId)!;
          const levels = expectedLevels(model);

          expect(choice?.modelId).toBe(expectedId);
          if (levels.length === 0) {
            expect(choice?.effort).toBeNull();
          } else if (expectedId === storedId && storedEffort !== null && levels.includes(storedEffort)) {
            expect(choice?.effort).toBe(storedEffort);
          } else {
            expect(choice?.effort).toBe(c.default_efforts[expectedId]);
          }
        },
      ),
      PROPERTY_OPTIONS,
    );
  });

  it("notes a stored model that is no longer offered", () => {
    fc.assert(
      fc.property(
        catalog.filter((c) => c.models.length > 0),
        optionalId,
        (c, preferredId) => {
          const { note } = preselect({
            response: c,
            stored: { modelId: GONE_ID, effort: null },
            preferredModelId: preferredId,
          });

          expect(note).toEqual({ kind: "stored_model_unavailable", storedModelId: GONE_ID });
        },
      ),
      PROPERTY_OPTIONS,
    );
  });

  it("is generated with a model-less catalog too", () => {
    // Guards the generator: the empty-list branch of the property above must be reachable.
    const sample = fc.sample(catalog, { seed: PROPERTY_OPTIONS.seed, numRuns: 500 });
    expect(sample.some((c) => c.models.length === 0)).toBe(true);
    const hiddenLevels = (m: CapabilityModelEntry) =>
      m.reasoning_mode === "none" && (m.reasoning_levels?.length ?? 0) > 0;
    expect(sample.some((c) => c.models.some(hiddenLevels))).toBe(true);
  });
});
