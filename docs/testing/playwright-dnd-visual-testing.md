# Playwright Drag-and-Drop Visual Testing Guide

How to capture screenshots during drag-and-drop operations for visual QA.

## The Challenge

Playwright's built-in `dragTo()` method completes instantly, making it impossible to capture intermediate visual states like drop indicators. To test visual feedback during drag operations, we need manual mouse control.

## Solution: Manual Mouse Control

Use `page.mouse` methods to control the drag manually with pauses for screenshots.

### Basic Pattern

```javascript
async (page) => {
  // 1. Get elements
  const sourceCard = page.getByRole("button", {
    name: "Story: CSV bulk import",
  });
  const targetColumn = page.locator(".kanban-column").nth(1);

  // 2. Get bounding boxes
  const sourceBox = await sourceCard.boundingBox();
  const targetBox = await targetColumn.boundingBox();

  // 3. Start drag
  await page.mouse.move(
    sourceBox.x + sourceBox.width / 2,
    sourceBox.y + sourceBox.height / 2,
  );
  await page.mouse.down();

  // 4. Move slowly (steps controls smoothness)
  await page.mouse.move(
    targetBox.x + targetBox.width / 2,
    targetBox.y + 100, // Offset into the column
    { steps: 20 }, // Smooth movement
  );

  // 5. Pause for visual state to settle
  await page.waitForTimeout(500);

  // 6. Capture screenshot
  await page.screenshot({ path: ".playwright-mcp/drop-indicator-test.png" });

  // 7. Complete drag
  await page.mouse.up();

  return "Screenshot captured during drag";
};
```

### Testing Drop Indicator Over Existing Card

To trigger the drop indicator to appear above another card:

```javascript
async (page) => {
  const sourceCard = page.getByRole("button", {
    name: "Story: CSV bulk import",
  });
  const targetCard = page.getByRole("button", {
    name: "Story: Analytics report",
  });

  const sourceBox = await sourceCard.boundingBox();
  const targetBox = await targetCard.boundingBox();

  // Start drag
  await page.mouse.move(
    sourceBox.x + sourceBox.width / 2,
    sourceBox.y + sourceBox.height / 2,
  );
  await page.mouse.down();

  // Move to hover over target card center
  await page.mouse.move(
    targetBox.x + targetBox.width / 2,
    targetBox.y + targetBox.height / 2,
    { steps: 15 },
  );

  // Wait for React state updates and animations
  await page.waitForTimeout(800);

  // Capture
  await page.screenshot({ path: ".playwright-mcp/drop-indicator-hover.png" });

  await page.mouse.up();
  return "Captured hover state";
};
```

## Key Parameters

| Parameter            | Purpose                                                            |
| -------------------- | ------------------------------------------------------------------ |
| `steps`              | Number of intermediate mouse positions (higher = smoother, slower) |
| `waitForTimeout`     | Pause in ms to let animations/state settle before screenshot       |
| Bounding box offsets | Control where in the element the mouse lands                       |

## Tips

1. **Use `steps: 15-20`** for smooth, visible movement
2. **Wait 500-800ms** after moving before screenshot to let animations complete
3. **Target the center** of elements for reliable hit detection
4. **Offset into columns** (e.g., `targetBox.y + 100`) to position within drop zones
5. **Test both themes** - run the same test in light and dark mode

## Running in Claude Code

Use the `browser_run_code` MCP tool:

```
mcp__plugin_developer-kit_playwright__browser_run_code
```

Pass the async function as the `code` parameter.

## Screenshot Location

Screenshots are saved to `.playwright-mcp/` in the project root. Add this to `.gitignore` if not already present.
