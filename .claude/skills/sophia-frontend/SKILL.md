---
name: frontend
identity: ./IDENTITY.md
triggers:
  keywords:
    - frontend
    - ui
    - streamlit
    - next
    - react
    - component
    - webapp
    - story
    - board
    - dashboard
    - theme
    - styling
  file_patterns:
    - frontend/**/*.py
    - webapp/**/*.tsx
    - webapp/**/*.ts
    - webapp/src/app/**
    - webapp/src/components/**
dependencies:
  skills:
    - learning-loop
  tools:
    - Bash
    - Read
    - Write
---

# Frontend Development Skill

Build intuitive, accessible user interfaces for Story Tracking Web App (Next.js) and Streamlit Dashboard.

## Workflow

### Phase 1: Understand Requirements

1. **Identify Application**
   - Story Tracking Web App (Next.js/React) - `webapp/`
   - Streamlit Dashboard (Python) - `frontend/`

2. **Load Context**
   - For webapp: `docs/story-tracking-web-app-architecture.md`
   - Review existing component patterns
   - Check API contracts with backend

3. **INVOKE `/frontend-design` SKILL** (MANDATORY for webapp UI)
   - Get design system guidance
   - Review component patterns
   - Ensure accessibility standards

### Phase 2: Design UI

1. **Review Existing Patterns**
   - For webapp: Check `webapp/src/components/` for similar components
   - For Streamlit: Check `frontend/pages/` for page structure
   - Follow established styling and layout conventions

2. **Plan Components**
   - Component hierarchy
   - Props and state management
   - API data requirements
   - Loading and error states

3. **Consider Accessibility**
   - Keyboard navigation
   - Screen reader compatibility
   - Color contrast (light/dark themes)
   - Semantic HTML

### Phase 3: Implement

#### For Next.js Web App

1. **Use Existing Patterns**
   - shadcn/ui components from registry
   - Tailwind CSS for styling
   - `useTheme()` hook for theme-aware components
   - TypeScript for type safety

2. **Component Structure**

   ```typescript
   // Type-safe props
   interface ComponentProps {
     data: DataType;
     onAction: (id: string) => void;
   }

   export function Component({ data, onAction }: ComponentProps) {
     // Loading state
     // Error handling
     // Main render
   }
   ```

3. **Theme Awareness**
   - Use `useTheme()` for theme-dependent logic
   - Reference `FeedForwardLogo.tsx` for theme-aware assets
   - Test in both light and dark modes

#### For Streamlit Dashboard

1. **Use Existing Patterns**
   - Consistent page structure from `frontend/pages/`
   - `api_client.py` for backend calls
   - Session state management

2. **Page Structure**

   ```python
   import streamlit as st
   from api_client import APIClient

   st.header("Page Title")

   # Initialize session state
   if 'key' not in st.session_state:
       st.session_state.key = default_value

   # API calls via client
   client = APIClient()
   data = client.get_data()

   # Display with tabs
   tab1, tab2 = st.tabs(["Tab 1", "Tab 2"])
   ```

### Phase 4: Verify

1. **Manual Testing**
   - Run the application locally
   - Test with real API data
   - Verify loading states appear during API calls
   - Test error scenarios (API failures, invalid data)

2. **Accessibility Check**
   - [ ] Keyboard navigation works (Tab, Enter, Escape)
   - [ ] Works in both light and dark themes
   - [ ] Color contrast is sufficient
   - [ ] Screen reader labels present

3. **Cross-Check**
   - For webapp: No TypeScript errors
   - For Streamlit: No Python runtime errors
   - API integration works correctly

## Success Criteria

Before claiming completion:

- [ ] UI works with real data from API
- [ ] Loading states shown during API calls
- [ ] Error states handled gracefully with user-friendly messages
- [ ] Works in both light and dark themes (webapp)
- [ ] Keyboard navigation functional
- [ ] No TypeScript errors (webapp)
- [ ] Page renders without errors in browser
- [ ] Responsive design tested (if applicable)

## Constraints

- **DO NOT** touch backend code (`src/`, `src/api/`) - Marcus's domain
- **DO NOT** modify API endpoints - Marcus's domain
- **DO NOT** write test files - Kenji's domain (unless specifically asked)
- **ALWAYS** test UI manually in both light and dark modes (webapp)
- **ALWAYS** check keyboard accessibility
- **ALWAYS** invoke `/frontend-design` skill for webapp UI components
- **ALWAYS** use existing component patterns, don't reinvent

## Key Files & Patterns

### Story Tracking Web App (Next.js)

| Directory                                   | Purpose                  |
| ------------------------------------------- | ------------------------ |
| `webapp/src/app/`                           | Next.js App Router pages |
| `webapp/src/components/`                    | React components         |
| `webapp/src/app/globals.css`                | Global styles and theme  |
| `webapp/src/components/FeedForwardLogo.tsx` | Theme-aware logo example |

**Pattern**: Theme-aware component

```typescript
import { useTheme } from 'next-themes';

export function ThemedComponent() {
  const { theme } = useTheme();

  return (
    <div className={theme === 'dark' ? 'dark-specific' : 'light-specific'}>
      {/* Content */}
    </div>
  );
}
```

**Pattern**: shadcn/ui usage

```typescript
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';

export function StoryCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Title</CardTitle>
      </CardHeader>
      <CardContent>
        <Button variant="outline">Action</Button>
      </CardContent>
    </Card>
  );
}
```

### Streamlit Dashboard (Legacy)

| Directory                | Purpose             |
| ------------------------ | ------------------- |
| `frontend/app.py`        | Main entry point    |
| `frontend/pages/`        | Dashboard pages     |
| `frontend/api_client.py` | Backend API wrapper |

**Pattern**: API integration

```python
from api_client import APIClient

def load_data():
    client = APIClient()
    try:
        return client.get_themes()
    except Exception as e:
        st.error(f"Failed to load data: {e}")
        return []
```

## Common Pitfalls

- **Webapp: Not checking theme**: Components must work in both light and dark modes
- **Webapp: Missing TypeScript types**: All props and state should be typed
- **Streamlit: Missing API client calls**: Always use `api_client.py`, don't call APIs directly
- **Streamlit: Session state not initialized**: Check for key existence before accessing
- **Missing loading states**: Always show feedback during async operations
- **Poor error messages**: Generic errors don't help users

## If Blocked

If you cannot proceed:

1. State what you're stuck on
2. Explain what's not working (include error messages or screenshots)
3. Share what you've already tried
4. Provide component/page context
5. Ask the Tech Lead for guidance
