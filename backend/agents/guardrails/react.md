# React Component Rules

## Component Style

- Use functional components exclusively. Class components are not permitted.
- Export one component per file. The file name must match the component name in PascalCase.
- Keep components focused on a single responsibility. Extract sub-components when a component exceeds ~150 lines.

## Props

- Define all props with a TypeScript `interface` named `{ComponentName}Props`.
- Mark props that must not be mutated as `readonly`.
- Provide default values for optional props via destructuring defaults, not `defaultProps`.
- Never pass raw `any` as a prop type.

## Hooks

- Call hooks only at the top level of a component or custom hook — never inside loops, conditions, or nested functions.
- Extract reusable stateful logic into custom hooks prefixed with `use`.
- Declare all dependencies in `useEffect`, `useCallback`, and `useMemo` dependency arrays accurately.
- Avoid `useEffect` for data transformations that can be computed during render.

## State Management

- Prefer local state (`useState`) for UI-only state.
- Lift state to the nearest common ancestor when two sibling components need to share it.
- Use `useReducer` for complex state transitions with multiple sub-values.

## Accessibility

- Every interactive element must be keyboard-operable and have a visible focus indicator.
- Provide `aria-label` or `aria-labelledby` on icon-only buttons and controls without visible text.
- Use semantic HTML elements (`<button>`, `<nav>`, `<main>`, `<section>`) rather than `<div>` with click handlers.
- Images must have descriptive `alt` text; decorative images use `alt=""`.
- Colour contrast must meet WCAG 2.1 AA (4.5:1 for normal text, 3:1 for large text).

## Performance

- Wrap expensive computations in `useMemo`; wrap stable callback references in `useCallback`.
- Use `React.lazy` and `Suspense` for route-level code splitting.
- Avoid inline object and array literals in JSX props — they create new references on every render.

## Code Style

- Use Tailwind CSS utility classes for styling. Avoid inline `style` props except for dynamic values.
- Keep JSX readable: one prop per line when a component has more than two props.
- Prefer early returns over deeply nested conditional rendering.
