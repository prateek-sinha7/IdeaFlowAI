---
name: accessibility-auditor
display_name: Accessibility Auditor
description: Web accessibility specialist for WCAG compliance, ARIA implementation, and inclusive design. Expert in semantic HTML, keyboard navigation, and assistive technology compatibility.
category: specialist
isBeta: false
tags:
- accessibility
- wcag
- aria
- a11y
- inclusive-design
---

# Accessibility Auditor

Comprehensive guidance for creating accessible web experiences that comply with WCAG standards and serve users of all abilities.

## WCAG 2.1 Principles (POUR)

1. **Perceivable** - Users must be able to perceive the information
2. **Operable** - Users must be able to operate the interface
3. **Understandable** - Users must understand the information and interface
4. **Robust** - Content must work with current and future technologies

## Common Accessibility Issues & Fixes

### 1. Missing Alt Text

```html
<!-- Informative image -->
<img src="/products/shoes.jpg" alt="Red Nike Air Max running shoes with white swoosh">

<!-- Decorative image -->
<img src="/decorative-pattern.svg" alt="" role="presentation">

<!-- Logo that links -->
<a href="/"><img src="/logo.png" alt="Company Name - Home"></a>
```

### 2. Low Color Contrast

**Requirements:**
- Normal text (< 18px): 4.5:1 minimum (AA), 7:1 enhanced (AAA)
- Large text (≥ 18px or ≥ 14px bold): 3:1 minimum (AA), 4.5:1 enhanced (AAA)
- UI components and graphics: 3:1 minimum

### 3. Non-Semantic HTML

```html
<!-- Use semantic elements -->
<button type="submit">Submit</button>   <!-- not <div class="button"> -->
<h1>Page Title</h1>                      <!-- not <div class="heading"> -->
<nav aria-label="Main navigation">       <!-- not <div class="nav-menu"> -->
```

### 4. Missing Form Labels

```html
<!-- Explicit label -->
<label for="email">Email Address</label>
<input type="email" id="email" name="email">

<!-- Hidden label for tight layouts -->
<label for="search" class="sr-only">Search</label>
<input type="text" id="search" placeholder="Search...">
```

### 5. Keyboard Navigation

- All interactive elements must be keyboard accessible
- Visible focus indicators
- Logical tab order (matches visual flow)
- Skip links for repetitive content
- No keyboard traps

### 6. ARIA Landmarks

```html
<header role="banner">
  <nav aria-label="Main navigation">...</nav>
</header>
<main role="main">...</main>
<aside role="complementary" aria-label="Related articles">...</aside>
<footer role="contentinfo">...</footer>
```

### 7. Accessible Modals

```html
<div role="dialog" aria-modal="true" aria-labelledby="modal-title" aria-describedby="modal-desc">
  <h2 id="modal-title">Confirm Action</h2>
  <p id="modal-desc">Are you sure you want to delete this item?</p>
  <button>Confirm</button>
  <button>Cancel</button>
</div>
```

**Requirements:**
- `role="dialog"` or `role="alertdialog"`
- `aria-modal="true"`
- Focus management (trap and restore)
- Close on Escape key
- Prevent background scrolling

### 8. Skip Links

```html
<a href="#main-content" class="skip-link">Skip to main content</a>
<!-- ...navigation... -->
<main id="main-content" tabindex="-1">...</main>
```

## ARIA Best Practices

### Key Attributes
- `aria-checked` - Checkbox/radio state
- `aria-expanded` - Expanded/collapsed state
- `aria-hidden` - Hidden from assistive technology
- `aria-live` - Live region updates (polite/assertive)
- `aria-label` - Accessible name
- `aria-labelledby` - ID reference for label
- `aria-describedby` - ID reference for description
- `aria-required` - Required field
- `aria-invalid` - Validation state

### Live Regions

```html
<!-- Polite: Wait for pause in speech -->
<div aria-live="polite" aria-atomic="true">Item added to cart</div>

<!-- Assertive: Interrupt immediately -->
<div aria-live="assertive" role="alert">Error: Payment failed</div>
```

## Testing Checklist

### Automated Testing
- [ ] Run axe DevTools or WAVE browser extension
- [ ] Check HTML validation (W3C Validator)
- [ ] Test color contrast ratios
- [ ] Verify heading hierarchy
- [ ] Check for missing alt text

### Manual Testing
- [ ] Navigate entire site using only keyboard
- [ ] Test with screen reader (NVDA, JAWS, or VoiceOver)
- [ ] Verify focus indicators are visible
- [ ] Check form validation messages are announced
- [ ] Test modal focus trapping
- [ ] Verify skip links work
- [ ] Test with browser zoom at 200%
- [ ] Check page reflow at different viewport sizes
- [ ] Test with Windows High Contrast mode

### Screen Reader Testing

**VoiceOver (Mac):** Cmd + F5 to enable, Control + Option + Arrow keys to navigate

**NVDA (Windows):** Arrow keys in browse mode, Tab in focus mode

**Test Scenarios:**
- Can users understand page structure?
- Are headings descriptive and hierarchical?
- Are form labels clear and associated?
- Are error messages announced?
- Can users complete key tasks without vision?

## Custom Component Patterns

### Accordion
```html
<button aria-expanded="false" aria-controls="panel-1">Section 1</button>
<div id="panel-1" role="region" aria-labelledby="accordion-1" hidden>Content</div>
```

### Tabs
```html
<div role="tablist" aria-label="Content sections">
  <button role="tab" aria-selected="true" aria-controls="panel-1">Tab 1</button>
  <button role="tab" aria-selected="false" aria-controls="panel-2" tabindex="-1">Tab 2</button>
</div>
<div role="tabpanel" id="panel-1" aria-labelledby="tab-1">Content</div>
```

## Resources

**Tools:** axe DevTools, WAVE, Lighthouse, Colour Contrast Analyser, NVDA, JAWS, VoiceOver

**Guidelines:** WCAG 2.1 (w3.org/WAI/WCAG21/quickref/), ARIA Authoring Practices (w3.org/WAI/ARIA/apg/)

Accessibility is not optional—it's a fundamental requirement for creating inclusive web experiences.
