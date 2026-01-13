"use client";

import { useCallback } from "react";
import type { ResearchSourceType } from "@/lib/types";
import { SOURCE_TYPE_CONFIG } from "@/lib/types";

type FilterOption = "all" | ResearchSourceType;

interface SourceFilterProps {
  selected: FilterOption;
  onChange: (filter: FilterOption) => void;
}

const FILTER_OPTIONS: { value: FilterOption; label: string }[] = [
  { value: "all", label: "All Sources" },
  { value: "coda_page", label: "Coda Research" },
  { value: "coda_theme", label: "Coda Themes" },
  { value: "intercom", label: "Intercom Support" },
];

export function SourceFilter({ selected, onChange }: SourceFilterProps) {
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent, option: FilterOption) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        onChange(option);
      }
    },
    [onChange],
  );

  return (
    <div
      className="source-filter"
      role="radiogroup"
      aria-label="Filter by source"
    >
      {FILTER_OPTIONS.map((option) => {
        const isSelected = selected === option.value;
        const config =
          option.value !== "all"
            ? SOURCE_TYPE_CONFIG[option.value as ResearchSourceType]
            : null;

        return (
          <button
            key={option.value}
            className={`filter-chip ${isSelected ? "selected" : ""}`}
            onClick={() => onChange(option.value)}
            onKeyDown={(e) => handleKeyDown(e, option.value)}
            role="radio"
            aria-checked={isSelected}
            tabIndex={0}
            style={
              isSelected && config
                ? {
                    backgroundColor: config.bgColor,
                    color: config.color,
                    borderColor: config.color,
                  }
                : undefined
            }
          >
            {option.value !== "all" && (
              <span
                className="filter-dot"
                style={{
                  backgroundColor: config?.color || "var(--text-tertiary)",
                }}
              />
            )}
            {option.label}
          </button>
        );
      })}

      <style jsx>{`
        .source-filter {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }

        .filter-chip {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 8px 14px;
          background: var(--bg-surface);
          border: 1px solid var(--border-default);
          border-radius: var(--radius-full);
          color: var(--text-secondary);
          font-size: 13px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .filter-chip:hover {
          background: var(--bg-elevated);
          color: var(--text-primary);
          border-color: var(--border-strong);
        }

        .filter-chip:focus-visible {
          outline: 2px solid var(--accent-blue);
          outline-offset: 2px;
        }

        .filter-chip.selected {
          background: var(--accent-blue-dim);
          color: var(--accent-blue);
          border-color: var(--accent-blue);
        }

        .filter-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          flex-shrink: 0;
        }

        :global([data-theme="light"]) .filter-chip {
          background: var(--bg-surface);
        }

        :global([data-theme="light"]) .filter-chip:hover {
          background: var(--bg-hover);
        }

        :global([data-theme="light"]) .filter-chip.selected {
          background: var(--accent-blue-dim);
        }
      `}</style>
    </div>
  );
}

export type { FilterOption };
