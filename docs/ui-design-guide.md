# UI Design Guide: Colors, Depth, and Spacing

A comprehensive guide synthesized from Sajid's (@whosajid) UI design tutorials.

---

## Table of Contents

1. [Philosophy](#philosophy)
2. [Color System](#color-system)
3. [Creating Depth](#creating-depth)
4. [Spacing System](#spacing-system)
5. [Quick Reference](#quick-reference)

---

## Philosophy

> "It takes a lot less effort to take an average design to good tier than it is to take a good design to S tier."

Like video game graphics settings: the jump from Normal to High is dramatic, but High to Ultra costs a lot more performance for minimal visible improvement. **Depth is the "High setting" sweet spot** — maximum impact for minimal effort.

### Core Principles

1. **Colors are the easiest part** — the tricky bit is knowing when to stop playing
2. **Depth transforms boring UIs** — just a few shades + shadows
3. **Spacing creates hierarchy** — group related, separate distinct
4. **Consistency beats perfection** — even "wrong" values look okay if consistent

---

## Color System

### Color Format: HSL over Hex/RGB

**Never use hex or RGB for palette creation.** They don't make mathematical sense.

```css
/* BAD: These look similar but values are unrelated */
#0a0a0a, #141414, #1e1e1e

/* GOOD: Values tell you exactly what's happening */
hsl(0, 0%, 0%)    /* Black */
hsl(0, 0%, 5%)    /* +5% lighter */
hsl(0, 0%, 10%)   /* +10% lighter */
```

**HSL Breakdown:**

- **H (Hue)**: 0-360 on the color wheel
- **S (Saturation)**: 0-100% intensity
- **L (Lightness)**: 0-100% dark to light

For neutral palettes: set H and S to 0, then only adjust L.

### OKLCH: The Modern Alternative

Tailwind V4 uses OKLCH as the default. It handles lightness changes more naturally than HSL.

```css
/* OKLCH format */
oklch(L C H)
/* L: 0-1 (lightness) */
/* C: 0-0.4 (chroma, like saturation - rarely need >0.15) */
/* H: 0-360 (hue) */
```

**HSL vs OKLCH**: HSL loses saturation in very dark/light shades. OKLCH maintains more natural color increments.

### The Complete Color Palette

You only need these colors for any UI:

| Category          | Purpose                          |
| ----------------- | -------------------------------- |
| **Neutrals**      | Background, text, borders        |
| **Primary/Brand** | Main actions, character          |
| **Semantic**      | States (success, warning, error) |

### Dark Mode Colors

Start with these lightness values:

```css
:root {
  /* Backgrounds (light on top = closer to user) */
  --bg-base: hsl(0, 0%, 0%); /* 0% - page background */
  --bg-surface: hsl(0, 0%, 5%); /* 5% - cards, surfaces */
  --bg-raised: hsl(0, 0%, 10%); /* 10% - elevated elements */

  /* Text (sharp for headings, muted for body) */
  --text-primary: hsl(0, 0%, 90%); /* NOT 100% - too harsh */
  --text-secondary: hsl(0, 0%, 65%); /* Muted, still legible */

  /* Borders & Effects */
  --border: hsl(0, 0%, 15%);
  --highlight: hsl(0, 0%, 20%); /* Top border glow */
}
```

### Light Mode Colors

**Formula**: Subtract lightness from 100, then swap semantics.

```css
[data-theme="light"] {
  /* Note: "bg-dark" is now the LIGHTEST, "bg-light" is DARKEST */
  --bg-base: hsl(0, 0%, 100%); /* 100 - 0 = 100 */
  --bg-surface: hsl(0, 0%, 95%); /* 100 - 5 = 95 */
  --bg-raised: hsl(0, 0%, 90%); /* 100 - 10 = 90 */

  --text-primary: hsl(0, 0%, 10%);
  --text-secondary: hsl(0, 0%, 35%);
}
```

**Key insight**: Name variables semantically (bg-base, bg-surface, bg-raised) not visually (bg-dark, bg-light) so they work in both themes.

### Adding Character with Hue & Saturation

After establishing neutral shades, add subtle hue/saturation:

```css
/* Cool blue-gray palette */
--bg-base: hsl(220, 10%, 5%);
--bg-surface: hsl(220, 8%, 10%);
--bg-raised: hsl(220, 6%, 15%);

/* Warm beige palette */
--bg-base: hsl(30, 8%, 5%);
--bg-surface: hsl(30, 6%, 10%);
--bg-raised: hsl(30, 4%, 15%);
```

### CSS Implementation

```css
/* Dark mode (default) */
:root {
  --bg-base: hsl(0, 0%, 0%);
  --bg-surface: hsl(0, 0%, 5%);
  --bg-raised: hsl(0, 0%, 10%);
  --text-primary: hsl(0, 0%, 90%);
  --text-secondary: hsl(0, 0%, 65%);
}

/* Light mode */
@media (prefers-color-scheme: light) {
  :root {
    --bg-base: hsl(0, 0%, 95%);
    --bg-surface: hsl(0, 0%, 100%);
    --bg-raised: hsl(0, 0%, 100%);
    --text-primary: hsl(0, 0%, 10%);
    --text-secondary: hsl(0, 0%, 35%);
  }
}

/* Or use a data attribute for user toggle */
[data-theme="light"] {
  /* light mode overrides */
}
```

---

## Creating Depth

### The Two-Step Process

1. **Create 3-4 shades** of the same color (increment lightness by ~5-10%)
2. **Add shadows** using the layered shadow technique

That's it. This alone transforms "boring" to "polished."

### Layering with Lightness

```css
/* Each layer increases lightness by ~5% */
.page {
  background: hsl(0, 0%, 5%);
}
.card {
  background: hsl(0, 0%, 10%);
}
.button {
  background: hsl(0, 0%, 15%);
}
```

**Rule**: Lighter elements appear on top and feel closer to the user. Use them for important/interactive elements.

### The Shadow System

#### Level 1: Subtle (most use cases)

```css
.shadow-sm {
  box-shadow:
    inset 0 1px 0 0 hsla(0, 0%, 100%, 0.05),
    /* Light top edge */ 0 1px 3px 0 hsla(0, 0%, 0%, 0.3); /* Dark bottom shadow */
}
```

#### Level 2: Medium

```css
.shadow-md {
  box-shadow:
    inset 0 1px 0 0 hsla(0, 0%, 100%, 0.08),
    0 4px 6px -1px hsla(0, 0%, 0%, 0.3),
    0 2px 4px -1px hsla(0, 0%, 0%, 0.2);
}
```

#### Level 3: Large (modals, dropdowns)

```css
.shadow-lg {
  box-shadow:
    inset 0 1px 0 0 hsla(0, 0%, 100%, 0.1),
    0 10px 15px -3px hsla(0, 0%, 0%, 0.3),
    0 4px 6px -2px hsla(0, 0%, 0%, 0.2);
}
```

### Shadow Principles

1. **Combine soft + dark shadows** — more realistic than single shadow
2. **Light inset on top** — simulates light hitting raised surface
3. **Dark shadow on bottom** — simulates cast shadow
4. **Use transparency** (hsla) — shadows should never be pure black

### Raised vs Sunken Elements

**Raised** (cards, buttons, modals):

```css
.raised {
  box-shadow:
    inset 0 1px 0 0 hsla(0, 0%, 100%, 0.1),
    /* Light top */ 0 4px 6px hsla(0, 0%, 0%, 0.3); /* Dark bottom */
}
```

**Sunken** (inputs, progress bar tracks, tables):

```css
.sunken {
  box-shadow:
    inset 0 2px 4px hsla(0, 0%, 0%, 0.2),
    /* Dark top (pushed in) */ inset 0 -1px 0 hsla(0, 0%, 100%, 0.05); /* Light bottom edge */
}
```

### Gradients for Depth

```css
.card {
  background: linear-gradient(
    to bottom,
    hsl(0, 0%, 12%),
    /* Lighter top */ hsl(0, 0%, 8%) /* Darker bottom */
  );
}

/* Reveal full gradient on hover */
.card:hover {
  background: linear-gradient(to bottom, hsl(0, 0%, 15%), hsl(0, 0%, 8%));
}
```

### Light Mode Depth

In light mode:

- **Borders blend in** — use matching background color
- **Highlights go white** — bump lightness all the way up
- **Shadows are essential** — they do the heavy lifting

```css
[data-theme="light"] .card {
  background: white;
  border: 1px solid hsl(0, 0%, 90%); /* Subtle border */
  box-shadow:
    0 1px 3px hsla(0, 0%, 0%, 0.08),
    0 4px 12px hsla(0, 0%, 0%, 0.05);
}

[data-theme="light"] .card:hover {
  box-shadow:
    0 4px 12px hsla(0, 0%, 0%, 0.1),
    0 8px 24px hsla(0, 0%, 0%, 0.08);
}
```

### When to Remove Borders

When using color to create layers, borders become redundant:

```css
/* Instead of border on everything... */
.card {
  border: 1px solid var(--border);
}

/* ...use background color difference */
.page {
  background: hsl(0, 0%, 5%);
}
.card {
  background: hsl(0, 0%, 10%);
} /* No border needed */
```

---

## Spacing System

### Use REM, Not Pixels

```css
/* BAD: Doesn't scale with user preferences */
gap: 16px;

/* GOOD: Scales with font size */
gap: 1rem;
```

### The Spacing Scale

Increment by 0.25rem (4px at default 16px base):

| Value   | Pixels | Use Case                                         |
| ------- | ------ | ------------------------------------------------ |
| 0.25rem | 4px    | Tight grouping (icon + label)                    |
| 0.5rem  | 8px    | Related elements, inner spacing                  |
| 0.75rem | 12px   | List items, form fields                          |
| 1rem    | 16px   | **Most common**: buttons, cards, general padding |
| 1.25rem | 20px   | Comfortable padding                              |
| 1.5rem  | 24px   | Section separation                               |
| 2rem    | 32px   | Major section breaks                             |

### The Golden Rule: Inner < Outer

**Inner spacing must always be smaller than outer spacing.**

```css
/* CORRECT */
.button {
  padding: 0.5rem 1rem; /* Outer: 0.5rem vertical, 1rem horizontal */
  gap: 0.5rem; /* Inner: icon to text */
}

/* WRONG - feels broken */
.button {
  padding: 0.5rem;
  gap: 1rem; /* Inner > Outer = ugly */
}
```

### Grouping vs Separating

| Action                       | Spacing  | Example                       |
| ---------------------------- | -------- | ----------------------------- |
| **Group** related elements   | < 1rem   | Title + subtitle: 0.25-0.5rem |
| **Separate** distinct groups | 1.5-2rem | Form sections                 |
| **General padding/gaps**     | 1rem     | Card padding, button gaps     |

```css
.form-section {
  padding: 1.5rem; /* Outer padding */
  gap: 1.5rem; /* Between groups */
}

.form-group {
  gap: 0.5rem; /* Between label + input */
}

.button-group {
  gap: 1rem; /* Between related buttons */
}
```

### Start Big, Then Reduce

**Wrong approach**: Start with 0.5rem, increase if cramped
**Right approach**: Start with 1.5rem, decrease if wasteful

```css
/* Start generous */
.card {
  padding: 1.5rem;
  gap: 1rem;
}

/* Then tighten if needed */
.card-compact {
  padding: 1rem;
  gap: 0.75rem;
}
```

> "A little extra white space will only make things easier to read. But tighter spacing can literally hurt user experience."

### Optical Weight: Vertical vs Horizontal Padding

Text has more visual noise horizontally (varying letter widths) than vertically (consistent cap height). Therefore:

**Horizontal padding should be 2-3x vertical padding for buttons.**

```css
/* CORRECT: Horizontal > Vertical */
.button {
  padding: 0.5rem 1rem; /* 0.5 vertical, 1 horizontal */
}

.button-large {
  padding: 0.75rem 1.5rem; /* 2x ratio */
}

/* For elements with vertical content, use equal padding */
.card {
  padding: 1.25rem; /* Equal on all sides */
}
```

### Matching Padding with Border Radius

The same values that work for spacing also work for border-radius:

```css
.card {
  padding: 1rem;
  border-radius: 0.75rem; /* Slightly less than padding */
}

.button {
  padding: 0.5rem 1rem;
  border-radius: 0.5rem;
}
```

### The Three-Value System

If the full scale feels overwhelming, just use these three:

| Value        | Purpose                               |
| ------------ | ------------------------------------- |
| **0.5rem**   | Grouping closely related elements     |
| **1rem**     | Padding, button gaps, general spacing |
| **1.5-2rem** | Separating sections                   |

These three values handle 90% of spacing needs.

---

## Quick Reference

### Color Cheat Sheet

```css
:root {
  /* Backgrounds (dark mode) */
  --bg-base: hsl(0, 0%, 0%);
  --bg-surface: hsl(0, 0%, 5%);
  --bg-raised: hsl(0, 0%, 10%);

  /* Text */
  --text-primary: hsl(0, 0%, 90%);
  --text-secondary: hsl(0, 0%, 65%);

  /* Borders & Highlights */
  --border: hsl(0, 0%, 15%);
  --highlight: hsl(0, 0%, 20%);
}
```

### Shadow Cheat Sheet

```css
/* Small - buttons, cards */
--shadow-sm:
  inset 0 1px 0 hsla(0, 0%, 100%, 0.05), 0 1px 3px hsla(0, 0%, 0%, 0.3);

/* Medium - hover states */
--shadow-md:
  inset 0 1px 0 hsla(0, 0%, 100%, 0.08), 0 4px 6px hsla(0, 0%, 0%, 0.25);

/* Large - modals, dropdowns */
--shadow-lg:
  inset 0 1px 0 hsla(0, 0%, 100%, 0.1), 0 10px 15px hsla(0, 0%, 0%, 0.3);

/* Sunken - inputs, tracks */
--shadow-inset: inset 0 2px 4px hsla(0, 0%, 0%, 0.2);
```

### Spacing Cheat Sheet

```css
:root {
  --space-xs: 0.25rem; /* 4px - tight */
  --space-sm: 0.5rem; /* 8px - grouping */
  --space-md: 1rem; /* 16px - general */
  --space-lg: 1.5rem; /* 24px - sections */
  --space-xl: 2rem; /* 32px - major breaks */
}
```

### Decision Tree

**Picking Colors:**

1. Set H=0, S=0 for neutrals
2. Create 3 background shades: 0%, 5%, 10% lightness
3. Create 2 text shades: 90% (primary), 65% (secondary)
4. Add hue/saturation for brand feel
5. Flip for light mode (subtract from 100)

**Adding Depth:**

1. Identify important/interactive elements
2. Give them lighter background
3. Add shadow: light inset top + dark shadow bottom
4. Remove borders if color difference is clear

**Setting Spacing:**

1. Break UI into groups
2. Start with 1.5rem between groups
3. Use 0.5rem within groups
4. Ensure inner < outer spacing
5. Use 2-3x horizontal padding on buttons

---

## Resources

- [Sajid's UI Colors Tool](https://www.iamsajid.com/ui-colors/)
- [Sajid's Color Generator](https://www.iamsajid.com/colors/)
- [Sajid's 3 Shadows CodePen](https://codepen.io/whosajid/pen/LEGRBzp)
- [OKLCH Color Picker](https://oklch.com/)

---

_Guide synthesized from Sajid's YouTube tutorials: "The Easy Way to Pick UI Colors", "The Easy Way to Fix Boring UIs", and "The Easy Way to Pick Right Spacing"._
