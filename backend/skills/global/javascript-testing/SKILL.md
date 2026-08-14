---
name: javascript-testing
display_name: JavaScript Testing Patterns
description: Implement comprehensive testing strategies using Jest, Vitest, and Testing Library for unit, integration, and end-to-end testing.
category: testing
isBeta: false
tags:
- jest
- vitest
- testing-library
- tdd
- mocking
- integration-tests
- typescript
- coverage
---

# JavaScript Testing Patterns

Comprehensive guide for implementing robust testing strategies in JavaScript/TypeScript applications using modern testing frameworks.

## When to Use This Skill

- Setting up test infrastructure for new projects
- Writing unit tests for functions and classes
- Creating integration tests for APIs and services
- Implementing end-to-end tests for user flows
- Mocking external dependencies and APIs
- Testing React, Vue, or other frontend components
- Implementing test-driven development (TDD)
- Setting up continuous testing in CI/CD pipelines

## Framework Setup

### Vitest (Recommended)

```typescript
// vitest.config.ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    globals: true,
    environment: "node",
    coverage: {
      provider: "v8",
      reporter: ["text", "json", "html"],
      exclude: ["**/*.d.ts", "**/*.config.ts", "**/dist/**"],
    },
    setupFiles: ["./src/test/setup.ts"],
  },
});
```

### Jest

```typescript
// jest.config.ts
import type { Config } from "jest";

const config: Config = {
  preset: "ts-jest",
  testEnvironment: "node",
  roots: ["<rootDir>/src"],
  testMatch: ["**/__tests__/**/*.ts", "**/?(*.)+(spec|test).ts"],
  coverageThreshold: {
    global: { branches: 80, functions: 80, lines: 80, statements: 80 },
  },
};

export default config;
```

## Testing Patterns

### Unit Testing

```typescript
describe("calculateTotal", () => {
  it("should sum item prices with tax", () => {
    const items = [
      { price: 10, quantity: 2 },
      { price: 5, quantity: 1 },
    ];
    expect(calculateTotal(items, 0.1)).toBe(27.5);
  });

  it("should return 0 for empty cart", () => {
    expect(calculateTotal([], 0.1)).toBe(0);
  });
});
```

### Mocking

```typescript
import { vi } from "vitest";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

beforeEach(() => {
  mockFetch.mockResolvedValue({
    ok: true,
    json: () => Promise.resolve({ data: "test" }),
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});
```

### Integration Testing

```typescript
import request from "supertest";
import { app } from "../app";

describe("POST /api/users", () => {
  it("should create a user and return 201", async () => {
    const response = await request(app)
      .post("/api/users")
      .send({ name: "Test", email: "test@example.com" });

    expect(response.status).toBe(201);
    expect(response.body).toHaveProperty("id");
  });
});
```

## Best Practices

1. **Arrange-Act-Assert**: Structure tests clearly
2. **Test Behavior, Not Implementation**: Focus on what, not how
3. **Descriptive Names**: Test names should explain expected behavior
4. **Isolated Tests**: No shared state between tests
5. **Fast Feedback**: Keep unit tests under 100ms each
6. **Coverage Goals**: 80%+ coverage as a guideline, not a rule
7. **Mock Boundaries**: Mock external services, not internal modules
