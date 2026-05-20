# Web Accessibility Rules (WCAG 2.1 AA)

## Target Standard

All interfaces must meet WCAG 2.1 Level AA as a minimum.
Document the target explicitly in the accessibility plan section of any UX or design output.

## Colour and Contrast

- Normal text (under 18pt / 14pt bold): minimum contrast ratio of 4.5:1 against its background.
- Large text (18pt+ or 14pt+ bold): minimum contrast ratio of 3:1.
- UI components and graphical objects (icons, chart lines, input borders): minimum 3:1 against adjacent colours.
- Never convey information by colour alone — pair colour with a text label, icon, or pattern.

## Keyboard Navigation

- Every interactive element must be reachable and operable by keyboard alone.
- Tab order must follow the visual reading order of the page.
- Provide a visible focus indicator on every focusable element — never use `outline: none` without a replacement.
- Modal dialogs must trap focus while open and return focus to the trigger element on close.
- Provide skip-navigation links so keyboard users can bypass repeated navigation blocks.

## Semantic HTML and ARIA

- Use native HTML elements for their intended purpose: `<button>` for actions, `<a>` for navigation, `<input>` for form fields.
- Add ARIA roles, states, and properties only when native semantics are insufficient.
- Every form field must have a programmatically associated `<label>` (via `for`/`id` or wrapping).
- Icon-only buttons must have `aria-label` describing the action.
- Dynamic content updates must be announced via `aria-live` regions where appropriate.
- Landmark regions (`<main>`, `<nav>`, `<header>`, `<footer>`, `<aside>`) must be present and unique where required.

## Images and Media

- Informative images require descriptive `alt` text that conveys the same information as the image.
- Decorative images use `alt=""` so screen readers skip them.
- Videos must have captions; audio-only content must have a transcript.

## Motion and Animation

- Respect the `prefers-reduced-motion` media query — disable or reduce non-essential animations.
- Do not use content that flashes more than three times per second.

## Testing

- Run automated checks with axe-core or Lighthouse Accessibility audit on every page.
- Supplement with manual keyboard-only navigation testing.
- Test with at least one screen reader (NVDA + Chrome or VoiceOver + Safari) on critical user journeys.
- Accessibility issues rated Critical or Serious must be resolved before release.
