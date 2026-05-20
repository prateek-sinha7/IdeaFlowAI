# TypeScript Coding Rules

## Strict Mode

All TypeScript files must compile with `strict: true` in `tsconfig.json`.
This enables `strictNullChecks`, `noImplicitAny`, `strictFunctionTypes`, and related checks.
Never disable strict mode for a file or project.

## Type Declarations

- Prefer `interface` over `type` alias for object shapes that may be extended.
- Use `type` for unions, intersections, and mapped types.
- Never use `any`. Use `unknown` when the type is genuinely unknown, then narrow it.
- Never use non-null assertion (`!`) unless you have verified the value cannot be null at that point.
- Avoid type casting with `as` except when narrowing after a type guard.

## Functions and Parameters

- Annotate all function parameters and return types explicitly.
- Use `readonly` on parameters and properties that must not be mutated.
- Prefer named function declarations over anonymous arrow functions for top-level exports.
- Use `async`/`await` instead of raw Promise chains.

## Imports and Exports

- Use named exports; avoid default exports except for Next.js pages and React components.
- Group imports: external packages first, then internal modules, then types.
- Use path aliases (e.g., `@/components`) rather than deep relative paths.

## Error Handling

- Always handle Promise rejections — never leave a floating `Promise` without `.catch` or `await`.
- Use typed error classes rather than throwing plain strings.
- Narrow `unknown` errors in catch blocks before accessing properties.

## Code Style

- Maximum line length: 100 characters.
- Use `const` by default; use `let` only when reassignment is required.
- Destructure objects and arrays where it improves readability.
- Avoid magic numbers — extract constants with descriptive names.
- All files must end with a newline.
