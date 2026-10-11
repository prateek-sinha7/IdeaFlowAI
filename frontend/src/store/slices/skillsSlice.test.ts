import { beforeEach, describe, expect, it, vi } from "vitest";
import { configureStore } from "@reduxjs/toolkit";
import type { GlobalSkillEntry, SkillsLibraryResponse } from "@/store/api/skills";

const { library } = vi.hoisted(() => ({ library: vi.fn() }));

// System boundary: the HTTP adapter the thunk calls.
vi.mock("@/store/api/skills", () => ({ skillsLibraryApi: { library } }));

import skillsReducer, { fetchSkills, skillsCleared, type SkillsState } from "./skillsSlice";

const SKILL: GlobalSkillEntry = {
  id: "tdd",
  name: "tdd",
  display_name: "Test-driven development",
  description: "Write the test first",
  content: "red green refactor",
  category: "testing",
  tags: ["quality"],
};

function makeStore() {
  return configureStore({ reducer: { skills: skillsReducer } });
}

const INITIAL: SkillsState = {
  skills: [],
  totalCount: 0,
  skillCategories: [],
  status: "idle",
  error: null,
};

describe("skillsSlice", () => {
  beforeEach(() => {
    library.mockReset();
  });

  it("returns the idle empty state when initialised", () => {
    expect(skillsReducer(undefined, { type: "@@INIT" })).toEqual(INITIAL);
  });

  describe("fetchSkills", () => {
    it("sets status to loading and clears a previous error when pending", async () => {
      const store = makeStore();
      library.mockRejectedValueOnce(new Error("boom"));
      await store.dispatch(fetchSkills());
      expect(store.getState().skills.error).toBe("boom");

      let resolve!: (value: SkillsLibraryResponse) => void;
      library.mockReturnValueOnce(new Promise<SkillsLibraryResponse>((r) => (resolve = r)));
      const pending = store.dispatch(fetchSkills());

      expect(store.getState().skills.status).toBe("loading");
      expect(store.getState().skills.error).toBeNull();

      resolve({ skills: [], total_count: 0, categories: [], sources: [] });
      await pending;
    });

    it("stores skills, total count and categories when fulfilled", async () => {
      library.mockResolvedValueOnce({
        skills: [SKILL],
        total_count: 1,
        categories: [{ id: "testing", label: "Testing" }],
        sources: [],
      });
      const store = makeStore();

      await store.dispatch(fetchSkills());

      expect(store.getState().skills).toEqual({
        skills: [SKILL],
        totalCount: 1,
        skillCategories: [{ id: "testing", label: "Testing" }],
        status: "succeeded",
        error: null,
      });
    });

    it("falls back to empty collections when the payload omits every field", async () => {
      library.mockResolvedValueOnce({});
      const store = makeStore();

      await store.dispatch(fetchSkills());

      expect(store.getState().skills).toEqual({ ...INITIAL, status: "succeeded" });
    });

    it("records the error message when rejected with an Error", async () => {
      library.mockRejectedValueOnce(new Error("Network down"));
      const store = makeStore();

      await store.dispatch(fetchSkills());

      expect(store.getState().skills.status).toBe("failed");
      expect(store.getState().skills.error).toBe("Network down");
    });

    it("uses the default error message when the rejection carries no message", async () => {
      library.mockRejectedValueOnce({});
      const store = makeStore();

      await store.dispatch(fetchSkills());

      expect(store.getState().skills.status).toBe("failed");
      expect(store.getState().skills.error).toBe("Failed to fetch skills");
    });

    it("keeps previously loaded skills when a later fetch is rejected", async () => {
      library.mockResolvedValueOnce({ skills: [SKILL], total_count: 1, categories: [], sources: [] });
      const store = makeStore();
      await store.dispatch(fetchSkills());

      library.mockRejectedValueOnce(new Error("later failure"));
      await store.dispatch(fetchSkills());

      expect(store.getState().skills.skills).toEqual([SKILL]);
      expect(store.getState().skills.status).toBe("failed");
    });
  });

  describe("skillsCleared", () => {
    it("resets a populated slice back to the idle initial state", () => {
      const populated: SkillsState = {
        skills: [SKILL],
        totalCount: 1,
        skillCategories: [{ id: "testing", label: "Testing" }],
        status: "failed",
        error: "stale error",
      };

      expect(skillsReducer(populated, skillsCleared())).toEqual(INITIAL);
    });
  });
});
