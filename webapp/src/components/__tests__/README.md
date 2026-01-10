# Drag-and-Drop Test Suite

Comprehensive test coverage for the Story Tracking Web App's drag-and-drop implementation.

## Test Files

### 1. `dnd.types.test.ts` - Unit Tests

**Location**: `src/lib/__tests__/dnd.types.test.ts`
**Coverage**: 100% (statements, branches, functions, lines)

Tests for type helper functions and ID formatters:

- `createDraggableId()` - Creates draggable IDs in format `story-{id}`
- `createDroppableId()` - Creates droppable IDs in format `column-{status}`
- `extractStoryId()` - Extracts story ID from draggable ID
- Type safety validation for template literal types

**Key Test Cases** (19 tests):

- Correct ID format generation
- UUID handling
- Special character handling
- Roundtrip create/extract operations
- TypeScript type constraints

### 2. `DndBoardProvider.test.tsx` - Integration Tests

**Location**: `src/components/__tests__/DndBoardProvider.test.tsx`
**Coverage**: 26% (integration tests, not full handler coverage)

Tests for the drag context provider and state management:

- Context initialization and default values
- `useDragContext` hook functionality
- Drag event handler structure
- ARIA live region for screen reader announcements
- Error handling for failed moves
- State management for drag operations

**Key Test Cases** (16 tests):

- Initial context values (draggedCardHeight, isDragging, overColumn, overStoryId)
- Children rendering
- Context consumption from nested components
- ARIA accessibility features
- Error recovery after failed moves
- Multiple live regions (ours + dnd-kit's)

**Note**: Coverage is intentionally lower because full drag simulation requires dnd-kit test utilities. These tests validate the provider structure, context API, and error handling.

### 3. `DroppableColumn.test.tsx` - Component Tests

**Location**: `src/components/__tests__/DroppableColumn.test.tsx`
**Coverage**: 100% (statements), 90% (branches)

Tests for column rendering and drop zone behavior:

- Column header rendering (status label, indicator, count)
- Story card rendering and ordering
- Drop indicator behavior (over card, between cards, bottom of column)
- Empty column drop zones
- Accessibility features
- Visual styling

**Key Test Cases** (29 tests):

- Status labels for all 5 states (candidate, triaged, in_progress, done, dismissed)
- Story count display (0, multiple)
- Status indicator colors
- Card rendering with sortable wrappers
- Drop indicator visibility (shown when isOver=true, hidden at 0px otherwise)
- draggedCardHeight-based sizing
- Empty column placeholder vs indicator
- Bottom drop indicator (column end)
- Keyboard interaction support
- Semantic HTML structure

## Test Architecture

### Mocking Strategy

**dnd-kit Hooks**:

```typescript
mockUseSortable - Controls card drag state (isDragging, isOver)
mockUseDragContext - Controls global drag state (overColumn, overStoryId, draggedCardHeight)
```

**Component Mocks**:

- `framer-motion` - Simplified to remove animation complexity
- `StoryCard` - Simplified to just render title for easier testing
- `DndBoardProvider` - Mocked in column tests to avoid nested context

### Test Patterns

1. **Unit Tests** (`dnd.types.test.ts`)
   - Pure function testing
   - No mocks required
   - Roundtrip validation

2. **Integration Tests** (`DndBoardProvider.test.tsx`)
   - Context provider testing
   - Hook API validation
   - Error boundary testing

3. **Component Tests** (`DroppableColumn.test.tsx`)
   - Controlled mock state
   - Visual behavior verification
   - Accessibility validation

## Running Tests

```bash
# Run all tests
npm test

# Run with coverage
npm run test:coverage

# Watch mode
npm run test:watch

# Run specific test file
npm test -- DndBoardProvider.test.tsx
```

## Coverage Summary

| File                 | Statements | Branches | Functions | Lines |
| -------------------- | ---------- | -------- | --------- | ----- |
| dnd.types.ts         | 100%       | 100%     | 100%      | 100%  |
| DroppableColumn.tsx  | 100%       | 90%      | 100%      | 100%  |
| DndBoardProvider.tsx | 26%        | 3%       | 20%       | 26%   |

**Note**: DndBoardProvider coverage is lower because full drag simulation requires dnd-kit's testing utilities. The provider's event handlers (`handleDragStart`, `handleDragOver`, `handleDragEnd`, `handleDragCancel`) are tested structurally but not through actual drag operations.

## Key Behaviors Tested

### Type Helpers (dnd.types.ts)

- ✅ ID format consistency (`story-*`, `column-*`)
- ✅ Extract operations (story ID)
- ✅ TypeScript type safety
- ✅ Edge cases (empty strings, special characters, nested prefixes)

### Drag Context (DndBoardProvider.tsx)

- ✅ Context initialization
- ✅ Hook API (`useDragContext`)
- ✅ ARIA announcements
- ✅ Error handling
- ✅ State management
- ⚠️ Event handlers (structure tested, not full simulation)

### Column Component (DroppableColumn.tsx)

- ✅ Column header (status, indicator, count)
- ✅ Card rendering and ordering
- ✅ Drop indicators (card hover, column bottom, empty column)
- ✅ Indicator sizing (uses draggedCardHeight)
- ✅ Accessibility (semantic HTML, keyboard support)
- ✅ Visual states (dragging, hovering, idle)

## Accessibility Testing

All tests verify WCAG compliance:

- Screen reader announcements (ARIA live regions)
- Keyboard navigation support (tabIndex, role attributes)
- Semantic HTML (headings, proper structure)
- Focus management (focus-visible states)

## Future Enhancements

1. **E2E Drag Tests**: Use dnd-kit testing utilities for full drag simulation
2. **Visual Regression**: Screenshot testing for drop indicator states
3. **Performance**: Measure render performance during drag operations
4. **Touch Events**: Verify mobile touch interactions
5. **Keyboard Navigation**: Test full keyboard-only workflows

## Test Maintenance

When modifying DnD implementation:

1. Run tests to verify no regressions
2. Update mocks if hook signatures change
3. Add tests for new behaviors
4. Maintain 90%+ coverage on new code
5. Update this README with new patterns

## References

- [Jest Documentation](https://jestjs.io/)
- [React Testing Library](https://testing-library.com/react)
- [dnd-kit Testing Guide](https://docs.dndkit.com/guides/testing)
