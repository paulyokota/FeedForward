# UI Design System Refactor

Design specification for refactoring `webapp/src/app/globals.css` to align with Sajid's UI design principles.

**Author**: Priya (Architect)
**Status**: Design Complete
**Scope**: Single file change (`webapp/src/app/globals.css`)

---

## Summary

This refactor converts the FeedForward webapp's CSS design system from ad-hoc hex values and pixel units to a principled system using:

1. **HSL color format** with mathematical lightness progression
2. **Layered shadows** with light inset top + dark shadow bottom
3. **REM-based radius** for accessibility scaling
4. **Spacing system variables** using 0.25rem increments

The semantic variable names remain unchanged, so components require no modification.

---

## 1. Color System Conversion

### Current State (Hex)

```css
/* Current dark theme backgrounds */
--bg-void: #020617; /* ??? - no clear relationship */
--bg-primary: #0a1628; /* ??? */
--bg-surface: #132237; /* ??? */
--bg-elevated: #1c3049; /* ??? */
```

### Target State (HSL)

**Base Brand Values Extracted from Logo:**

- Primary Teal: `#22d3ee` = `hsl(187, 84%, 53%)`
- Slate Blue: `#1e3a5f` = `hsl(212, 52%, 25%)`

**Dark Mode Backgrounds** (slate-tinted, 5% lightness increments):

| Variable        | Current Hex | HSL Equivalent       | Lightness  |
| --------------- | ----------- | -------------------- | ---------- |
| `--bg-void`     | `#020617`   | `hsl(222, 84%, 4%)`  | ~4% (base) |
| `--bg-primary`  | `#0a1628`   | `hsl(216, 57%, 10%)` | ~10%       |
| `--bg-surface`  | `#132237`   | `hsl(214, 48%, 15%)` | ~15%       |
| `--bg-elevated` | `#1c3049`   | `hsl(212, 45%, 20%)` | ~20%       |
| `--bg-hover`    | `#264060`   | `hsl(212, 42%, 26%)` | ~26%       |
| `--bg-active`   | `#2f4d73`   | `hsl(212, 42%, 32%)` | ~32%       |

**Recommended HSL Values** (normalized to consistent hue/saturation):

```css
/* Dark mode backgrounds - Slate Blue tint (H=212) */
--bg-void: hsl(212, 60%, 3%); /* Deepest layer */
--bg-primary: hsl(212, 50%, 8%); /* Main background */
--bg-surface: hsl(212, 45%, 13%); /* Cards, panels */
--bg-elevated: hsl(212, 40%, 18%); /* Raised elements */
--bg-hover: hsl(212, 38%, 25%); /* Hover state */
--bg-active: hsl(212, 35%, 32%); /* Active/pressed */
```

**Text Colors:**

| Variable           | Current Hex | HSL Equivalent        |
| ------------------ | ----------- | --------------------- |
| `--text-primary`   | `#f0f9ff`   | `hsl(206, 100%, 97%)` |
| `--text-secondary` | `#94a3b8`   | `hsl(215, 16%, 65%)`  |
| `--text-tertiary`  | `#64748b`   | `hsl(215, 16%, 47%)`  |
| `--text-muted`     | `#475569`   | `hsl(215, 19%, 35%)`  |

```css
/* Dark mode text */
--text-primary: hsl(206, 100%, 97%); /* NOT 100% - too harsh */
--text-secondary: hsl(215, 16%, 65%);
--text-tertiary: hsl(215, 16%, 47%);
--text-muted: hsl(215, 19%, 35%);
```

**Accent Teal (Brand):**

```css
/* FeedForward Teal palette */
--accent-teal: hsl(187, 84%, 53%);
--accent-teal-bright: hsl(187, 92%, 69%);
--accent-teal-dim: hsla(187, 84%, 53%, 0.18);
```

### Light Mode Conversion Formula

**Formula**: `100 - L` for lightness, keep H and S similar.

```css
/* Light mode backgrounds */
--bg-void: hsl(212, 15%, 87%); /* 100 - 3 ~ 97, desaturated */
--bg-primary: hsl(0, 0%, 100%); /* Pure white */
--bg-surface: hsl(0, 0%, 100%); /* Pure white */
--bg-elevated: hsl(210, 40%, 96%); /* 100 - 18 ~ 96 */
--bg-hover: hsl(210, 40%, 89%); /* 100 - 25 ~ 89 */
--bg-active: hsl(212, 33%, 82%); /* 100 - 32 ~ 82 */

/* Light mode text (inverted) */
--text-primary: hsl(222, 47%, 11%);
--text-secondary: hsl(215, 25%, 27%);
--text-tertiary: hsl(215, 16%, 47%);
--text-muted: hsl(215, 16%, 65%);

/* Light mode teal - darker for contrast */
--accent-teal: hsl(187, 90%, 32%);
--accent-teal-bright: hsl(187, 85%, 40%);
```

### Border Conversion

**Dark mode borders** (using accent color with alpha):

```css
--border-subtle: hsla(187, 84%, 53%, 0.12);
--border-default: hsla(187, 84%, 53%, 0.2);
--border-strong: hsla(187, 84%, 53%, 0.35);
```

**Light mode borders** (using slate for subtlety):

```css
--border-subtle: hsla(215, 16%, 47%, 0.12);
--border-default: hsla(215, 16%, 47%, 0.2);
--border-strong: hsla(215, 16%, 47%, 0.35);
```

---

## 2. Shadow System

### Current State (Flat Shadows)

```css
/* Current - single layer, no depth */
--shadow-sm: 0 2px 4px rgba(0, 0, 0, 0.5);
--shadow-md: 0 4px 16px rgba(0, 0, 0, 0.6);
--shadow-lg: 0 8px 32px rgba(0, 0, 0, 0.7);
```

### Target State (Layered Shadows)

**Dark Mode Shadows** (light inset + dark bottom):

```css
/* Small - buttons, cards */
--shadow-sm:
  inset 0 1px 0 0 hsla(0, 0%, 100%, 0.05), 0 1px 3px 0 hsla(0, 0%, 0%, 0.3);

/* Medium - hover states, dropdowns */
--shadow-md:
  inset 0 1px 0 0 hsla(0, 0%, 100%, 0.08), 0 4px 6px -1px hsla(0, 0%, 0%, 0.3),
  0 2px 4px -1px hsla(0, 0%, 0%, 0.2);

/* Large - modals, overlays */
--shadow-lg:
  inset 0 1px 0 0 hsla(0, 0%, 100%, 0.1), 0 10px 15px -3px hsla(0, 0%, 0%, 0.3),
  0 4px 6px -2px hsla(0, 0%, 0%, 0.2);

/* Sunken - inputs, table rows, progress tracks */
--shadow-inset:
  inset 0 2px 4px 0 hsla(0, 0%, 0%, 0.2),
  inset 0 -1px 0 0 hsla(0, 0%, 100%, 0.05);

/* Brand glow - accent elements */
--shadow-glow: 0 0 24px hsla(187, 84%, 53%, 0.2);
```

**Light Mode Shadows** (softer, shadows do heavy lifting):

```css
/* Light mode - less inset, more ambient shadow */
--shadow-sm:
  0 1px 3px 0 hsla(0, 0%, 0%, 0.08), 0 1px 2px 0 hsla(0, 0%, 0%, 0.04);

--shadow-md:
  0 4px 6px -1px hsla(0, 0%, 0%, 0.1), 0 2px 4px -1px hsla(0, 0%, 0%, 0.05);

--shadow-lg:
  0 10px 15px -3px hsla(0, 0%, 0%, 0.1), 0 4px 6px -2px hsla(0, 0%, 0%, 0.05);

--shadow-inset: inset 0 2px 4px 0 hsla(0, 0%, 0%, 0.06);

--shadow-glow: none;
```

### Shadow Principles

1. **Light inset on top** - simulates light hitting raised surface (dark mode only)
2. **Dark shadow on bottom** - simulates cast shadow
3. **Multiple layers** - creates more realistic depth
4. **hsla transparency** - shadows blend naturally with any background

---

## 3. Spacing System

### Current State

No spacing variables defined. Components use arbitrary values.

### Target State

```css
:root {
  /* Spacing scale - 0.25rem increments */
  --space-xs: 0.25rem; /* 4px - tight grouping (icon + label) */
  --space-sm: 0.5rem; /* 8px - related elements, inner spacing */
  --space-md: 0.75rem; /* 12px - list items, form fields */
  --space-lg: 1rem; /* 16px - general padding, buttons */
  --space-xl: 1.5rem; /* 24px - section separation */
  --space-2xl: 2rem; /* 32px - major section breaks */
}
```

### Usage Guidelines

| Value         | Use Case                                   |
| ------------- | ------------------------------------------ |
| `--space-xs`  | Icon-to-text gap, badge padding            |
| `--space-sm`  | Input padding, list item padding           |
| `--space-md`  | Card content gap, form field gap           |
| `--space-lg`  | Card padding, button padding, section gaps |
| `--space-xl`  | Panel padding, major content separation    |
| `--space-2xl` | Page sections, layout margins              |

### Golden Rule: Inner < Outer

```css
/* CORRECT */
.card {
  padding: var(--space-lg); /* Outer: 1rem */
  gap: var(--space-md); /* Inner: 0.75rem */
}

/* WRONG */
.card {
  padding: var(--space-sm); /* Outer: 0.5rem */
  gap: var(--space-lg); /* Inner: 1rem - larger than outer! */
}
```

---

## 4. Radius Conversion

### Current State (Pixels)

```css
--radius-sm: 4px;
--radius-md: 6px;
--radius-lg: 10px;
```

### Target State (REM)

```css
--radius-sm: 0.25rem; /* 4px - buttons, inputs, tags */
--radius-md: 0.375rem; /* 6px - cards, dropdowns */
--radius-lg: 0.625rem; /* 10px - modals, panels */
--radius-xl: 1rem; /* 16px - large containers (NEW) */
--radius-full: 9999px; /* Pills, avatars (NEW) */
```

**Why REM?**

- Scales with user font size preferences (accessibility)
- Consistent with spacing system
- Maintains visual proportions at different zoom levels

---

## 5. File Boundaries

### Scope

**Single file change**: `webapp/src/app/globals.css`

### What Changes

| Section                                   | Change Type                    |
| ----------------------------------------- | ------------------------------ |
| `:root` variables                         | Values change, names stay same |
| `[data-theme="dark"]`                     | Values change, names stay same |
| `[data-theme="light"]`                    | Values change, names stay same |
| New spacing section                       | Add `--space-*` variables      |
| New radius `--radius-xl`, `--radius-full` | Add two new radius values      |

### What Stays Same

- All semantic variable names (`--bg-surface`, `--text-primary`, etc.)
- All component styles (`.story-card`, `.kanban-column`, etc.)
- All animations and utility classes
- Theme switching logic

### Components NOT Modified

No component files need changes because:

1. Variable names are semantic and unchanged
2. Components reference variables, not raw values
3. Light/dark theme switching continues to work

---

## 6. Migration Strategy

### Approach: Single Atomic Commit

This refactor can be completed in one commit because:

1. Only CSS custom property values change
2. Semantic variable names remain identical
3. No component code modifications required
4. Visual output should be nearly identical (refinement)

### Implementation Steps

1. **Backup current file** (git handles this)

2. **Update `:root` section**:
   - Convert all hex colors to HSL
   - Add spacing variables
   - Convert radius to REM
   - Add layered shadow system
   - Add `--shadow-inset` variable

3. **Update `[data-theme="dark"]` section**:
   - Mirror HSL conversions from `:root`
   - Apply dark mode shadow values

4. **Update `[data-theme="light"]` section**:
   - Apply light mode formula (100 - L)
   - Apply light mode shadow values

5. **Visual QA**:
   - Check all pages in dark mode
   - Check all pages in light mode
   - Verify hover/focus states
   - Test with browser zoom (50%, 100%, 200%)

### Commit Message

```
style(webapp): refactor design system to HSL + layered shadows

- Convert hex colors to HSL with mathematical lightness progression
- Add layered shadows (light inset + dark bottom) per Sajid's guide
- Convert radius from px to rem for accessibility scaling
- Add spacing system variables (--space-xs through --space-2xl)

Design spec: docs/webapp/ui-design-system-refactor.md
```

---

## 7. Complete CSS Variable Reference

### Dark Mode (Default)

```css
:root {
  /* Backgrounds - slate-tinted, 5% increments */
  --bg-void: hsl(212, 60%, 3%);
  --bg-primary: hsl(212, 50%, 8%);
  --bg-surface: hsl(212, 45%, 13%);
  --bg-elevated: hsl(212, 40%, 18%);
  --bg-hover: hsl(212, 38%, 25%);
  --bg-active: hsl(212, 35%, 32%);

  /* Text */
  --text-primary: hsl(206, 100%, 97%);
  --text-secondary: hsl(215, 16%, 65%);
  --text-tertiary: hsl(215, 16%, 47%);
  --text-muted: hsl(215, 19%, 35%);

  /* Borders - teal tinted */
  --border-subtle: hsla(187, 84%, 53%, 0.12);
  --border-default: hsla(187, 84%, 53%, 0.2);
  --border-strong: hsla(187, 84%, 53%, 0.35);

  /* FeedForward Teal */
  --accent-teal: hsl(187, 84%, 53%);
  --accent-teal-bright: hsl(187, 92%, 69%);
  --accent-teal-dim: hsla(187, 84%, 53%, 0.18);
  --accent-slate: hsl(212, 52%, 25%);

  /* Semantic accents */
  --accent-blue: hsl(187, 84%, 53%);
  --accent-blue-dim: hsla(187, 84%, 53%, 0.18);
  --accent-green: hsl(160, 64%, 52%);
  --accent-green-dim: hsla(160, 64%, 52%, 0.18);
  --accent-amber: hsl(43, 96%, 56%);
  --accent-amber-dim: hsla(43, 96%, 56%, 0.18);
  --accent-red: hsl(0, 91%, 68%);
  --accent-red-dim: hsla(0, 91%, 68%, 0.18);
  --accent-purple: hsl(258, 90%, 76%);
  --accent-purple-dim: hsla(258, 90%, 76%, 0.18);

  /* Priority colors */
  --priority-urgent: hsl(0, 91%, 68%);
  --priority-high: hsl(27, 96%, 61%);
  --priority-medium: hsl(43, 96%, 56%);
  --priority-low: hsl(215, 16%, 47%);

  /* Status colors */
  --status-candidate: hsl(258, 90%, 76%);
  --status-triaged: hsl(187, 84%, 53%);
  --status-in-progress: hsl(43, 96%, 56%);
  --status-done: hsl(160, 64%, 52%);
  --status-dismissed: hsl(215, 16%, 47%);

  /* Typography */
  --font-sans: var(--font-geist-sans), system-ui, -apple-system, sans-serif;
  --font-mono: var(--font-geist-mono), "SF Mono", Monaco, monospace;

  /* Spacing */
  --space-xs: 0.25rem;
  --space-sm: 0.5rem;
  --space-md: 0.75rem;
  --space-lg: 1rem;
  --space-xl: 1.5rem;
  --space-2xl: 2rem;

  /* Radius */
  --radius-sm: 0.25rem;
  --radius-md: 0.375rem;
  --radius-lg: 0.625rem;
  --radius-xl: 1rem;
  --radius-full: 9999px;

  /* Shadows - layered with light inset */
  --shadow-sm:
    inset 0 1px 0 0 hsla(0, 0%, 100%, 0.05), 0 1px 3px 0 hsla(0, 0%, 0%, 0.3);
  --shadow-md:
    inset 0 1px 0 0 hsla(0, 0%, 100%, 0.08),
    0 4px 6px -1px hsla(0, 0%, 0%, 0.3), 0 2px 4px -1px hsla(0, 0%, 0%, 0.2);
  --shadow-lg:
    inset 0 1px 0 0 hsla(0, 0%, 100%, 0.1),
    0 10px 15px -3px hsla(0, 0%, 0%, 0.3), 0 4px 6px -2px hsla(0, 0%, 0%, 0.2);
  --shadow-inset:
    inset 0 2px 4px 0 hsla(0, 0%, 0%, 0.2),
    inset 0 -1px 0 0 hsla(0, 0%, 100%, 0.05);
  --shadow-glow: 0 0 24px hsla(187, 84%, 53%, 0.2);

  --theme-mode: dark;
}
```

### Light Mode

```css
[data-theme="light"] {
  /* Backgrounds - inverted */
  --bg-void: hsl(180, 8%, 85%);
  --bg-primary: hsl(0, 0%, 100%);
  --bg-surface: hsl(0, 0%, 100%);
  --bg-elevated: hsl(210, 40%, 96%);
  --bg-hover: hsl(210, 40%, 89%);
  --bg-active: hsl(212, 33%, 82%);

  /* Text - inverted */
  --text-primary: hsl(222, 47%, 11%);
  --text-secondary: hsl(215, 25%, 27%);
  --text-tertiary: hsl(215, 16%, 47%);
  --text-muted: hsl(215, 16%, 65%);

  /* Borders - slate tinted */
  --border-subtle: hsla(215, 16%, 47%, 0.12);
  --border-default: hsla(215, 16%, 47%, 0.2);
  --border-strong: hsla(215, 16%, 47%, 0.35);

  /* Accents - darker for contrast */
  --accent-teal: hsl(187, 90%, 32%);
  --accent-teal-bright: hsl(187, 85%, 40%);
  --accent-teal-dim: hsla(187, 90%, 32%, 0.12);
  --accent-slate: hsl(212, 52%, 25%);

  --accent-blue: hsl(187, 90%, 32%);
  --accent-blue-dim: hsla(187, 90%, 32%, 0.12);
  --accent-green: hsl(160, 84%, 29%);
  --accent-green-dim: hsla(160, 84%, 29%, 0.12);
  --accent-amber: hsl(32, 95%, 44%);
  --accent-amber-dim: hsla(32, 95%, 44%, 0.12);
  --accent-red: hsl(0, 72%, 51%);
  --accent-red-dim: hsla(0, 72%, 51%, 0.12);
  --accent-purple: hsl(262, 83%, 58%);
  --accent-purple-dim: hsla(262, 83%, 58%, 0.12);

  /* Priority - darker for light bg */
  --priority-urgent: hsl(0, 72%, 51%);
  --priority-high: hsl(21, 90%, 48%);
  --priority-medium: hsl(32, 95%, 44%);
  --priority-low: hsl(215, 16%, 47%);

  /* Status - darker for light bg */
  --status-candidate: hsl(262, 83%, 58%);
  --status-triaged: hsl(187, 90%, 32%);
  --status-in-progress: hsl(32, 95%, 44%);
  --status-done: hsl(160, 84%, 29%);
  --status-dismissed: hsl(215, 16%, 47%);

  /* Shadows - softer, no inset */
  --shadow-sm:
    0 1px 3px 0 hsla(0, 0%, 0%, 0.08), 0 1px 2px 0 hsla(0, 0%, 0%, 0.04);
  --shadow-md:
    0 4px 6px -1px hsla(0, 0%, 0%, 0.1), 0 2px 4px -1px hsla(0, 0%, 0%, 0.05);
  --shadow-lg:
    0 10px 15px -3px hsla(0, 0%, 0%, 0.1), 0 4px 6px -2px hsla(0, 0%, 0%, 0.05);
  --shadow-inset: inset 0 2px 4px 0 hsla(0, 0%, 0%, 0.06);
  --shadow-glow: none;

  --theme-mode: light;
}
```

---

## 8. Acceptance Criteria

Before marking implementation complete, verify:

- [ ] All hex colors converted to HSL
- [ ] Background lightness follows ~5% increments
- [ ] Light mode uses (100 - L) formula consistently
- [ ] All shadows use layered technique (dark mode)
- [ ] `--shadow-inset` variable added
- [ ] All radii converted to REM
- [ ] Spacing variables `--space-xs` through `--space-2xl` added
- [ ] Visual appearance is consistent with current design
- [ ] Dark mode renders correctly
- [ ] Light mode renders correctly
- [ ] Theme toggle works without flash
- [ ] Browser zoom (50%, 100%, 200%) looks correct

---

## References

- [UI Design Guide](../ui-design-guide.md) - Source principles from Sajid
- [Current globals.css](../../webapp/src/app/globals.css) - Implementation target
