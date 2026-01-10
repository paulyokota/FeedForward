"use client";

import { useTheme } from "./ThemeProvider";

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  return (
    <div className="theme-toggle">
      <button
        className={`toggle-option ${theme === "light" ? "active" : ""}`}
        onClick={() => setTheme("light")}
        title="Light mode"
        aria-label="Light mode"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="theme-icon"
        >
          <circle cx="12" cy="12" r="5" />
          <line x1="12" y1="1" x2="12" y2="3" />
          <line x1="12" y1="21" x2="12" y2="23" />
          <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
          <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
          <line x1="1" y1="12" x2="3" y2="12" />
          <line x1="21" y1="12" x2="23" y2="12" />
          <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
          <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
        </svg>
      </button>

      <button
        className={`toggle-option ${theme === "system" ? "active" : ""}`}
        onClick={() => setTheme("system")}
        title="System preference"
        aria-label="System preference"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="theme-icon"
        >
          <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
          <line x1="8" y1="21" x2="16" y2="21" />
          <line x1="12" y1="17" x2="12" y2="21" />
        </svg>
      </button>

      <button
        className={`toggle-option ${theme === "dark" ? "active" : ""}`}
        onClick={() => setTheme("dark")}
        title="Dark mode"
        aria-label="Dark mode"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="theme-icon"
        >
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
        </svg>
      </button>

      <style jsx>{`
        .theme-toggle {
          display: flex;
          align-items: center;
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 32%),
            hsl(0, 0%, 28%)
          );
          border: none;
          border-radius: var(--radius-full);
          padding: 4px;
          gap: 2px;
          box-shadow: var(--shadow-sm);
        }

        :global([data-theme="light"]) .theme-toggle {
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 96%),
            hsl(0, 0%, 90%)
          );
          box-shadow: var(--shadow-inset);
        }

        .toggle-option {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 32px;
          height: 28px;
          border: none;
          background: transparent;
          border-radius: var(--radius-full);
          color: var(--text-tertiary);
          cursor: pointer;
          transition: all 0.2s ease;
        }

        .toggle-option:hover {
          color: var(--text-secondary);
          background: var(--bg-hover);
        }

        .toggle-option.active {
          background: var(--bg-surface);
          color: var(--text-primary);
          box-shadow: var(--shadow-sm);
        }

        .toggle-option:focus-visible {
          outline: 2px solid var(--accent-blue);
          outline-offset: 1px;
        }
      `}</style>
    </div>
  );
}
