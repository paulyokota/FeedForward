# Structured Description Component

## Overview

The `StructuredDescription` component provides an enhanced view for story descriptions on detail pages. It automatically parses markdown-style sections and presents them in a clean, organized format with progressive disclosure for long content.

## Features

### 1. Automatic Section Parsing

The component detects markdown bold headers (e.g., `**Summary**`, `**Impact**`, `**Evidence**`) and automatically structures the content into sections with proper headings and spacing.

**Example:**

```markdown
**Summary**
Users are experiencing login timeouts.

**Impact**

- High priority issue
- Affects 15% of users
- Workaround available

**Evidence**
Multiple support tickets reference this issue.
```

This is rendered as:

- **Summary** (section heading)
  - "Users are experiencing login timeouts." (content)
- **Impact** (section heading)
  - Bullet list with proper formatting
- **Evidence** (section heading)
  - Evidence content

### 2. View Toggle

Users can switch between two views:

- **Structured View** (default): Parsed sections with headings, proper spacing, and bullet formatting
- **Raw View**: Exact text as stored in the database

The toggle only appears when structured sections are detected. If the description contains no structured sections, it falls back to raw view automatically.

### 3. Progressive Disclosure

Long sections (more than 3 lines) are automatically truncated with a "Show more" button. Clicking expands the full content, and clicking "Show less" collapses it again.

This keeps the UI clean while allowing users to explore details when needed.

### 4. Copy Raw Description

A "Copy" button allows users to copy the raw description text to their clipboard. This is useful for:

- Pasting into tickets (e.g., Shortcut)
- Sharing with team members
- Using in documentation

The button shows "Copied!" feedback for 2 seconds after successful copy.

## Implementation

### Component Location

```
webapp/src/components/StructuredDescription.tsx
```

### Usage

```tsx
import { StructuredDescription } from "@/components/StructuredDescription";

<StructuredDescription description={story.description} />;
```

### Integration

The component is integrated into the story detail page at:

```
webapp/src/app/story/[id]/page.tsx
```

It replaces the previous `ReactMarkdown` component with a more tailored solution for our specific content structure.

## Testing

Tests are located at:

```
webapp/src/components/__tests__/StructuredDescription.test.tsx
```

Run tests with:

```bash
npm test -- StructuredDescription.test.tsx
```

### Test Coverage

- Section parsing and rendering
- Fallback to raw view for unstructured content
- View toggle functionality
- Progressive disclosure (expand/collapse)
- Clipboard copy functionality
- Bullet point rendering

## Design Decisions

### Why Not Use ReactMarkdown?

1. **Specific Structure**: Our descriptions follow a predictable pattern with section headers
2. **Progressive Disclosure**: We need custom truncation logic for long sections
3. **View Toggle**: Switching between structured and raw views requires custom state management
4. **Performance**: Simpler parsing is faster than full markdown rendering
5. **Copy Functionality**: Direct access to raw text for clipboard operations

### Parsing Strategy

The parser looks for `**Header**` patterns and extracts content between consecutive headers. This is simpler and more predictable than full markdown parsing, and matches how our LLM generates descriptions.

### Fallback Behavior

If no structured sections are detected, the component gracefully falls back to raw view. This ensures compatibility with:

- Legacy descriptions
- Manually edited descriptions
- Descriptions from different sources

## Future Enhancements

Possible improvements for future iterations:

1. **Link Detection**: Auto-link URLs in raw view
2. **Syntax Highlighting**: For code blocks if present
3. **Section Collapse**: Allow individual sections to be collapsed
4. **Print Friendly**: Optimize for printing story details
5. **Export Options**: Export as PDF or formatted text

## Related Components

- **EvidenceBrowser**: Similar progressive disclosure pattern
- **ImplementationContext**: Also uses section-based UI
- **ShortcutSyncPanel**: Another example of structured content display
