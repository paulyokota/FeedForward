"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { api } from "@/lib/api";
import type { LabelRegistryEntry } from "@/lib/types";

interface LabelPickerProps {
  selectedLabels: string[];
  onLabelsChange: (labels: string[]) => void;
  disabled?: boolean;
}

export function LabelPicker({
  selectedLabels,
  onLabelsChange,
  disabled = false,
}: LabelPickerProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [labels, setLabels] = useState<LabelRegistryEntry[]>([]);
  const [filteredLabels, setFilteredLabels] = useState<LabelRegistryEntry[]>(
    [],
  );
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [focusedIndex, setFocusedIndex] = useState(-1);
  const [isCreating, setIsCreating] = useState(false);

  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Debounce search query
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQuery(searchQuery);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  // Fetch labels on mount
  useEffect(() => {
    const fetchLabels = async () => {
      try {
        setIsLoading(true);
        setError(null);
        const response = await api.labels.list();
        setLabels(response.labels);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load labels");
      } finally {
        setIsLoading(false);
      }
    };

    if (isOpen && labels.length === 0) {
      fetchLabels();
    }
  }, [isOpen, labels.length]);

  // Filter labels based on search
  useEffect(() => {
    if (!debouncedQuery.trim()) {
      setFilteredLabels(labels);
    } else {
      const query = debouncedQuery.toLowerCase();
      setFilteredLabels(
        labels.filter((label) =>
          label.label_name.toLowerCase().includes(query),
        ),
      );
    }
    setFocusedIndex(-1);
  }, [debouncedQuery, labels]);

  // Handle click outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
        setSearchQuery("");
      }
    };

    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isOpen]);

  // Focus input when popover opens
  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isOpen]);

  // Scroll focused item into view
  useEffect(() => {
    if (focusedIndex >= 0 && listRef.current) {
      const items = listRef.current.querySelectorAll("[data-label-item]");
      const focusedItem = items[focusedIndex] as HTMLElement;
      if (focusedItem) {
        focusedItem.scrollIntoView({ block: "nearest" });
      }
    }
  }, [focusedIndex]);

  const handleToggle = () => {
    if (!disabled) {
      setIsOpen(!isOpen);
      if (!isOpen) {
        setSearchQuery("");
        setFocusedIndex(-1);
      }
    }
  };

  const handleLabelToggle = useCallback(
    (labelName: string) => {
      const isSelected = selectedLabels.includes(labelName);
      if (isSelected) {
        onLabelsChange(selectedLabels.filter((l) => l !== labelName));
      } else {
        onLabelsChange([...selectedLabels, labelName]);
      }
    },
    [selectedLabels, onLabelsChange],
  );

  const handleRemoveLabel = (labelName: string, e: React.MouseEvent) => {
    e.stopPropagation();
    onLabelsChange(selectedLabels.filter((l) => l !== labelName));
  };

  const handleCreateLabel = async () => {
    const trimmedQuery = searchQuery.trim();
    if (!trimmedQuery) return;

    try {
      setIsCreating(true);
      const newLabel = await api.labels.create({
        label_name: trimmedQuery,
        source: "internal",
      });
      setLabels((prev) => [...prev, newLabel]);
      onLabelsChange([...selectedLabels, newLabel.label_name]);
      setSearchQuery("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create label");
    } finally {
      setIsCreating(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isOpen) {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        setIsOpen(true);
      }
      return;
    }

    const itemCount = filteredLabels.length + (showCreateOption ? 1 : 0);

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        setFocusedIndex((prev) => (prev < itemCount - 1 ? prev + 1 : 0));
        break;
      case "ArrowUp":
        e.preventDefault();
        setFocusedIndex((prev) => (prev > 0 ? prev - 1 : itemCount - 1));
        break;
      case "Enter":
        e.preventDefault();
        if (focusedIndex >= 0 && focusedIndex < filteredLabels.length) {
          handleLabelToggle(filteredLabels[focusedIndex].label_name);
        } else if (focusedIndex === filteredLabels.length && showCreateOption) {
          handleCreateLabel();
        }
        break;
      case "Escape":
        e.preventDefault();
        setIsOpen(false);
        setSearchQuery("");
        break;
    }
  };

  const showCreateOption =
    searchQuery.trim() &&
    !filteredLabels.some(
      (l) => l.label_name.toLowerCase() === searchQuery.trim().toLowerCase(),
    );

  return (
    <div className="label-picker" ref={containerRef}>
      <button
        type="button"
        className="trigger-btn"
        onClick={handleToggle}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
      >
        {selectedLabels.length > 0 ? (
          <span className="selected-count">
            {selectedLabels.length} label
            {selectedLabels.length !== 1 ? "s" : ""} selected
          </span>
        ) : (
          <span className="placeholder">Add labels</span>
        )}
        <ChevronIcon isOpen={isOpen} />
      </button>

      {selectedLabels.length > 0 && (
        <div className="selected-chips">
          {selectedLabels.map((label) => (
            <span key={label} className="label-chip">
              {label}
              <button
                type="button"
                className="chip-remove"
                onClick={(e) => handleRemoveLabel(label, e)}
                aria-label={`Remove ${label}`}
              >
                <CloseIcon />
              </button>
            </span>
          ))}
        </div>
      )}

      {isOpen && (
        <div className="popover" role="listbox" onKeyDown={handleKeyDown}>
          <div className="search-wrapper">
            <SearchIcon />
            <input
              ref={inputRef}
              type="text"
              className="search-input"
              placeholder="Search labels..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              aria-label="Search labels"
            />
          </div>

          <div className="labels-list" ref={listRef}>
            {isLoading ? (
              <div className="loading-state">
                <div className="spinner" />
                <span>Loading labels...</span>
              </div>
            ) : error ? (
              <div className="error-state">{error}</div>
            ) : filteredLabels.length === 0 && !showCreateOption ? (
              <div className="empty-state">No labels found</div>
            ) : (
              <>
                {filteredLabels.map((label, index) => {
                  const isSelected = selectedLabels.includes(label.label_name);
                  const isFocused = index === focusedIndex;
                  return (
                    <button
                      key={label.label_name}
                      type="button"
                      className={`label-option ${isSelected ? "selected" : ""} ${isFocused ? "focused" : ""}`}
                      onClick={() => handleLabelToggle(label.label_name)}
                      data-label-item
                      role="option"
                      aria-selected={isSelected}
                    >
                      <div className="checkbox">
                        {isSelected && <CheckIcon />}
                      </div>
                      <span className="label-name">{label.label_name}</span>
                      {label.source === "shortcut" && (
                        <span
                          className="source-badge shortcut"
                          title="From Shortcut"
                        >
                          <ShortcutIcon />
                        </span>
                      )}
                    </button>
                  );
                })}

                {showCreateOption && (
                  <button
                    type="button"
                    className={`label-option create-option ${focusedIndex === filteredLabels.length ? "focused" : ""}`}
                    onClick={handleCreateLabel}
                    disabled={isCreating}
                    data-label-item
                  >
                    <PlusIcon />
                    <span className="create-text">
                      {isCreating
                        ? "Creating..."
                        : `Create "${searchQuery.trim()}"`}
                    </span>
                  </button>
                )}
              </>
            )}
          </div>
        </div>
      )}

      <style jsx>{`
        .label-picker {
          position: relative;
        }

        .trigger-btn {
          display: flex;
          align-items: center;
          justify-content: space-between;
          width: 100%;
          padding: 10px 12px;
          background: var(--bg-elevated);
          border: 1px solid var(--border-default);
          border-radius: var(--radius-md);
          color: var(--text-primary);
          font-size: 14px;
          cursor: pointer;
          transition: border-color 0.15s ease;
        }

        .trigger-btn:hover:not(:disabled) {
          border-color: var(--border-strong);
        }

        .trigger-btn:focus {
          outline: none;
          border-color: var(--accent-teal);
        }

        .trigger-btn:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }

        .placeholder {
          color: var(--text-muted);
        }

        .selected-count {
          color: var(--text-primary);
        }

        .selected-chips {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          margin-top: 8px;
        }

        .label-chip {
          display: inline-flex;
          align-items: center;
          gap: 4px;
          padding: 4px 8px;
          background: var(--bg-elevated);
          border: 1px solid var(--border-default);
          border-radius: var(--radius-full);
          font-size: 12px;
          color: var(--text-secondary);
        }

        .chip-remove {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 14px;
          height: 14px;
          padding: 0;
          background: transparent;
          border: none;
          color: var(--text-tertiary);
          cursor: pointer;
          border-radius: 50%;
          transition: all 0.15s ease;
        }

        .chip-remove:hover {
          background: var(--bg-hover);
          color: var(--text-primary);
        }

        .popover {
          position: absolute;
          top: calc(100% + 4px);
          left: 0;
          right: 0;
          background: var(--bg-surface);
          border: 1px solid var(--border-default);
          border-radius: var(--radius-lg);
          box-shadow: var(--shadow-lg);
          z-index: 50;
          overflow: hidden;
          animation: popoverIn 0.15s ease-out;
        }

        @keyframes popoverIn {
          from {
            opacity: 0;
            transform: translateY(-6px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        .search-wrapper {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 10px 12px;
          border-bottom: 1px solid var(--border-subtle);
        }

        .search-input {
          flex: 1;
          background: transparent;
          border: none;
          color: var(--text-primary);
          font-size: 13px;
          outline: none;
        }

        .search-input::placeholder {
          color: var(--text-muted);
        }

        .labels-list {
          max-height: 240px;
          overflow-y: auto;
          padding: 6px;
        }

        .loading-state,
        .error-state,
        .empty-state {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          padding: 16px;
          color: var(--text-secondary);
          font-size: 13px;
        }

        .error-state {
          color: var(--accent-red);
        }

        .spinner {
          width: 14px;
          height: 14px;
          border: 2px solid var(--border-default);
          border-top-color: var(--accent-teal);
          border-radius: 50%;
          animation: spin 0.8s linear infinite;
        }

        @keyframes spin {
          to {
            transform: rotate(360deg);
          }
        }

        .label-option {
          display: flex;
          align-items: center;
          gap: 10px;
          width: 100%;
          padding: 8px 10px;
          background: transparent;
          border: none;
          border-radius: var(--radius-md);
          color: var(--text-primary);
          font-size: 13px;
          text-align: left;
          cursor: pointer;
          transition: background 0.1s ease;
        }

        .label-option:hover,
        .label-option.focused {
          background: var(--bg-hover);
        }

        .label-option.selected {
          background: var(--accent-teal-dim, rgba(20, 184, 166, 0.1));
        }

        .checkbox {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 16px;
          height: 16px;
          border: 1.5px solid var(--border-default);
          border-radius: 4px;
          flex-shrink: 0;
          transition: all 0.15s ease;
        }

        .label-option.selected .checkbox {
          background: var(--accent-teal);
          border-color: var(--accent-teal);
        }

        .label-name {
          flex: 1;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .source-badge {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 18px;
          height: 18px;
          border-radius: 4px;
          flex-shrink: 0;
        }

        .source-badge.shortcut {
          background: var(--accent-purple-dim, rgba(168, 85, 247, 0.1));
          color: var(--accent-purple);
        }

        .create-option {
          color: var(--accent-teal);
          border-top: 1px solid var(--border-subtle);
          margin-top: 6px;
          padding-top: 12px;
        }

        .create-option:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }

        .create-text {
          flex: 1;
        }
      `}</style>
    </div>
  );
}

function ChevronIcon({ isOpen }: { isOpen: boolean }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{
        transform: isOpen ? "rotate(180deg)" : "rotate(0deg)",
        transition: "transform 0.15s ease",
      }}
    >
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="var(--text-tertiary)"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg
      width="10"
      height="10"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg
      width="10"
      height="10"
      viewBox="0 0 24 24"
      fill="none"
      stroke="white"
      strokeWidth="3"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

function ShortcutIcon() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
      <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  );
}
