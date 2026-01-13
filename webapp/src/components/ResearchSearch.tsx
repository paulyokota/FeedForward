"use client";

import { useState, useRef, useEffect, useCallback } from "react";

interface ResearchSearchProps {
  value: string;
  onChange: (value: string) => void;
  isSearching?: boolean;
  placeholder?: string;
  onClear?: () => void;
}

export function ResearchSearch({
  value,
  onChange,
  isSearching = false,
  placeholder = "Search research...",
  onClear,
}: ResearchSearchProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isFocused, setIsFocused] = useState(false);

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleClear = useCallback(() => {
    onChange("");
    onClear?.();
    inputRef.current?.focus();
  }, [onChange, onClear]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Escape" && value) {
        handleClear();
      }
    },
    [value, handleClear],
  );

  return (
    <div className={`research-search ${isFocused ? "focused" : ""}`}>
      <svg
        className="search-icon"
        width="20"
        height="20"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        aria-hidden="true"
      >
        <circle cx="11" cy="11" r="8" />
        <line x1="21" y1="21" x2="16.65" y2="16.65" />
      </svg>

      <input
        ref={inputRef}
        type="text"
        className="search-input"
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => setIsFocused(true)}
        onBlur={() => setIsFocused(false)}
        onKeyDown={handleKeyDown}
        aria-label="Search research"
      />

      {isSearching && (
        <div className="search-spinner" aria-label="Searching..." />
      )}

      {value && !isSearching && (
        <button
          className="search-clear"
          onClick={handleClear}
          aria-label="Clear search"
          type="button"
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      )}

      <style jsx>{`
        .research-search {
          position: relative;
          display: flex;
          align-items: center;
          width: 100%;
          max-width: 600px;
        }

        .search-icon {
          position: absolute;
          left: 16px;
          color: var(--text-muted);
          pointer-events: none;
          transition: color 0.15s ease;
        }

        .research-search.focused .search-icon {
          color: var(--accent-blue);
        }

        .search-input {
          width: 100%;
          padding: 14px 48px;
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 16%),
            hsl(0, 0%, 12%)
          );
          border: 1px solid var(--border-default);
          border-radius: var(--radius-lg);
          color: var(--text-primary);
          font-size: 15px;
          box-shadow: var(--shadow-sm);
          transition: all 0.15s ease;
        }

        :global([data-theme="light"]) .search-input {
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 100%),
            hsl(0, 0%, 97%)
          );
        }

        .search-input:focus {
          outline: none;
          border-color: var(--accent-blue);
          box-shadow: 0 0 0 3px var(--accent-blue-dim);
        }

        .search-input::placeholder {
          color: var(--text-muted);
        }

        .search-spinner {
          position: absolute;
          right: 16px;
          width: 18px;
          height: 18px;
          border: 2px solid var(--border-default);
          border-top-color: var(--accent-blue);
          border-radius: 50%;
          animation: spin 0.6s linear infinite;
        }

        .search-clear {
          position: absolute;
          right: 12px;
          background: none;
          border: none;
          color: var(--text-muted);
          cursor: pointer;
          padding: 6px;
          border-radius: var(--radius-sm);
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.15s ease;
        }

        .search-clear:hover {
          color: var(--text-primary);
          background: var(--bg-hover);
        }

        .search-clear:focus-visible {
          outline: 2px solid var(--accent-blue);
          outline-offset: 2px;
        }

        @keyframes spin {
          to {
            transform: rotate(360deg);
          }
        }
      `}</style>
    </div>
  );
}
