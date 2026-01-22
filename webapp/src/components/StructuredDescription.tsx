"use client";

import React, { useState } from "react";

interface StructuredDescriptionProps {
  description: string;
}

interface Section {
  title: string;
  content: string;
  isLong: boolean;
}

// Threshold for collapsing long sections (number of lines)
const LONG_SECTION_THRESHOLD = 5;

// Known section headers that should be treated as top-level sections
const KNOWN_SECTIONS = new Set([
  // Generic sections
  "summary",
  "impact",
  "evidence",
  "repro",
  "reproduction",
  "context",
  "notes",
  "description",
  "problem",
  "solution",
  "background",
  "details",
  "analysis",
  // Story-specific sections (from LLM output)
  "user story",
  "acceptance criteria",
  "symptoms",
  "symptoms (customer reported)",
  "technical notes",
  "invest check",
]);

/**
 * Parse description text into structured sections.
 * Supports both ## Header and **Bold** formats.
 * Only recognizes specific known headers to avoid over-fragmenting content.
 * Falls back to showing raw content if no known sections found.
 */
function parseDescription(description: string): Section[] | null {
  const parts: Array<{
    title: string;
    startIndex: number;
    contentIndex: number;
  }> = [];

  // Pattern 1: ## Markdown headers (e.g., "## User Story", "## Context")
  const markdownHeaderPattern = /(?:^|\n)##\s+([^\n]+)/g;
  let match;
  while ((match = markdownHeaderPattern.exec(description)) !== null) {
    const title = match[1].trim();
    if (KNOWN_SECTIONS.has(title.toLowerCase())) {
      parts.push({
        title,
        startIndex: match.index,
        contentIndex: match.index + match[0].length,
      });
    }
  }

  // Pattern 2: **Bold** headers (e.g., "**Summary**", "**Impact**")
  const boldHeaderPattern = /(?:^|\n)\s*\*\*([^*]+)\*\*:?\s*/g;
  while ((match = boldHeaderPattern.exec(description)) !== null) {
    const title = match[1].trim();
    if (KNOWN_SECTIONS.has(title.toLowerCase())) {
      parts.push({
        title,
        startIndex: match.index,
        contentIndex: match.index + match[0].length,
      });
    }
  }

  // Sort by position in document
  parts.sort((a, b) => a.startIndex - b.startIndex);

  // If no known sections found, return null to show raw view
  if (parts.length === 0) {
    return null;
  }

  const sections: Section[] = parts.map((part, idx) => {
    const nextStartIndex =
      idx < parts.length - 1 ? parts[idx + 1].startIndex : description.length;
    const content = description
      .substring(part.contentIndex, nextStartIndex)
      .trim();

    // Consider content "long" if it exceeds threshold
    const lineCount = content.split("\n").filter((line) => line.trim()).length;
    const isLong = lineCount > LONG_SECTION_THRESHOLD;

    return { title: part.title, content, isLong };
  });

  // Filter out empty sections
  return sections.filter((s) => s.content.length > 0);
}

/**
 * Render a single section with progressive disclosure for long content.
 */
function SectionContent({ section }: { section: Section }) {
  const [isExpanded, setIsExpanded] = useState(false);

  // Split into paragraphs (double newline) or lines
  const lines = section.content.split("\n").filter((line) => line.trim());
  const shouldTruncate = section.isLong && !isExpanded;
  const displayLines = shouldTruncate
    ? lines.slice(0, LONG_SECTION_THRESHOLD)
    : lines;
  const remainingCount = lines.length - LONG_SECTION_THRESHOLD;

  // Group consecutive bullet points together
  const renderContent = () => {
    const elements: React.ReactElement[] = [];
    let bulletGroup: string[] = [];

    const flushBullets = () => {
      if (bulletGroup.length > 0) {
        elements.push(
          <ul key={`bullets-${elements.length}`} className="bullet-list">
            {bulletGroup.map((item, i) => (
              <li key={i} className="bullet-item">
                {item}
              </li>
            ))}
          </ul>,
        );
        bulletGroup = [];
      }
    };

    displayLines.forEach((line, idx) => {
      const trimmed = line.trim();
      // Check for checkbox items first
      const checkboxMatch = trimmed.match(/^-\s*\[([ xX])\]\s*(.*)$/);
      const isBullet =
        trimmed.startsWith("-") ||
        trimmed.startsWith("•") ||
        trimmed.startsWith("*");

      if (checkboxMatch) {
        // Flush any pending bullets first
        flushBullets();
        const isChecked = checkboxMatch[1].toLowerCase() === "x";
        const text = checkboxMatch[2];
        elements.push(
          <div key={idx} className="checkbox-item">
            <span className={`checkbox ${isChecked ? "checked" : ""}`}>
              {isChecked ? "✓" : "○"}
            </span>
            <span className={isChecked ? "checked-text" : ""}>{text}</span>
          </div>,
        );
      } else if (isBullet) {
        // Remove bullet character and add to group
        bulletGroup.push(trimmed.replace(/^[-•*]\s*/, ""));
      } else {
        flushBullets();
        // Render bold text within paragraphs
        const boldPattern = /\*\*([^*]+)\*\*/g;
        const parts = trimmed.split(boldPattern);

        elements.push(
          <p key={idx} className="content-line">
            {parts.map((part, i) =>
              i % 2 === 1 ? <strong key={i}>{part}</strong> : part,
            )}
          </p>,
        );
      }
    });

    flushBullets();
    return elements;
  };

  return (
    <div className="section-content">
      <div className="content-text">{renderContent()}</div>

      {section.isLong && (
        <button
          type="button"
          className="expand-btn"
          onClick={() => setIsExpanded(!isExpanded)}
        >
          {isExpanded ? (
            <>
              <ChevronUpIcon />
              Show less
            </>
          ) : (
            <>
              <ChevronDownIcon />
              Show {remainingCount} more line{remainingCount !== 1 ? "s" : ""}
            </>
          )}
        </button>
      )}

      <style jsx>{`
        .section-content {
          margin-bottom: 16px;
        }

        .content-text {
          font-size: 14px;
          line-height: 1.6;
          color: var(--text-secondary);
        }

        .content-line {
          margin: 0 0 8px 0;
        }

        .content-line:last-child {
          margin-bottom: 0;
        }

        .bullet-list {
          margin: 8px 0;
          padding-left: 20px;
          list-style-type: disc;
        }

        .bullet-item {
          margin: 4px 0;
          color: var(--text-secondary);
          line-height: 1.5;
        }

        .checkbox-item {
          display: flex;
          align-items: flex-start;
          gap: 8px;
          margin: 6px 0;
          color: var(--text-secondary);
          line-height: 1.5;
        }

        .checkbox {
          flex-shrink: 0;
          width: 18px;
          height: 18px;
          display: flex;
          align-items: center;
          justify-content: center;
          border-radius: 4px;
          font-size: 12px;
          background: var(--bg-surface);
          border: 1px solid var(--border-default);
        }

        .checkbox.checked {
          background: var(--accent-teal, var(--accent-blue));
          border-color: var(--accent-teal, var(--accent-blue));
          color: white;
        }

        .checked-text {
          text-decoration: line-through;
          opacity: 0.7;
        }

        .expand-btn {
          display: flex;
          align-items: center;
          gap: 6px;
          margin-top: 12px;
          padding: 6px 12px;
          background: transparent;
          border: 1px dashed var(--border-default);
          border-radius: var(--radius-md);
          color: var(--text-secondary);
          font-size: 13px;
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .expand-btn:hover {
          background: var(--bg-hover);
          color: var(--text-primary);
          border-style: solid;
        }
      `}</style>
    </div>
  );
}

export function StructuredDescription({
  description,
}: StructuredDescriptionProps) {
  const [viewMode, setViewMode] = useState<"structured" | "raw">("structured");
  const [copyState, setCopyState] = useState<"idle" | "success" | "error">(
    "idle",
  );

  const sections = parseDescription(description);
  const shouldUseStructured = sections !== null && sections.length > 0;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(description);
      setCopyState("success");
      setTimeout(() => setCopyState("idle"), 2000);
    } catch (err) {
      console.error("Failed to copy:", err);
      setCopyState("error");
      setTimeout(() => setCopyState("idle"), 2000);
    }
  };

  return (
    <div className="structured-description">
      <div className="description-header">
        {shouldUseStructured && (
          <div className="view-toggle">
            <button
              type="button"
              className={`toggle-btn ${viewMode === "structured" ? "active" : ""}`}
              onClick={() => setViewMode("structured")}
            >
              Structured
            </button>
            <button
              type="button"
              className={`toggle-btn ${viewMode === "raw" ? "active" : ""}`}
              onClick={() => setViewMode("raw")}
            >
              Raw
            </button>
          </div>
        )}

        <button
          type="button"
          className={`copy-btn ${copyState === "error" ? "error" : ""}`}
          onClick={handleCopy}
          title="Copy raw description"
        >
          {copyState === "success" ? (
            <>
              <CheckIcon />
              Copied!
            </>
          ) : copyState === "error" ? (
            <>
              <CopyIcon />
              Failed
            </>
          ) : (
            <>
              <CopyIcon />
              Copy
            </>
          )}
        </button>
      </div>

      {viewMode === "structured" && shouldUseStructured ? (
        <div className="structured-view">
          {sections.map((section, idx) => (
            <div key={idx} className="section">
              <h3 className="section-title">{section.title}</h3>
              <SectionContent section={section} />
            </div>
          ))}
        </div>
      ) : (
        <div className="raw-view">
          <pre className="raw-text">{description}</pre>
        </div>
      )}

      <style jsx>{`
        .structured-description {
          margin-bottom: 16px;
        }

        .description-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 16px;
          gap: 12px;
        }

        .view-toggle {
          display: inline-flex;
          background: var(--bg-elevated);
          border: 1px solid var(--border-default);
          border-radius: var(--radius-md);
          padding: 2px;
        }

        .toggle-btn {
          padding: 6px 14px;
          background: transparent;
          border: none;
          border-radius: var(--radius-sm);
          color: var(--text-secondary);
          font-size: 13px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .toggle-btn:hover {
          color: var(--text-primary);
        }

        .toggle-btn.active {
          background: var(--bg-surface);
          color: var(--text-primary);
          box-shadow: var(--shadow-sm);
        }

        .copy-btn {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 6px 12px;
          background: var(--bg-surface);
          border: 1px solid var(--border-default);
          border-radius: var(--radius-md);
          color: var(--text-secondary);
          font-size: 13px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.15s ease;
          margin-left: auto;
        }

        .copy-btn:hover {
          background: var(--bg-hover);
          color: var(--text-primary);
          border-color: var(--accent-teal, var(--accent-blue));
        }

        .copy-btn.error {
          color: var(--status-error, #dc2626);
          border-color: var(--status-error, #dc2626);
        }

        .structured-view {
          display: flex;
          flex-direction: column;
          gap: 20px;
        }

        .section {
          padding-bottom: 16px;
          border-bottom: 1px solid var(--border-subtle);
        }

        .section:last-child {
          border-bottom: none;
          padding-bottom: 0;
        }

        .section-title {
          font-size: 16px;
          font-weight: 600;
          color: var(--text-primary);
          margin: 0 0 12px 0;
          padding-bottom: 8px;
          border-bottom: 1px solid var(--border-subtle);
        }

        .raw-view {
          background: var(--bg-surface);
          border: 1px solid var(--border-default);
          border-radius: var(--radius-md);
          padding: 16px;
        }

        .raw-text {
          font-family: var(--font-mono);
          font-size: 13px;
          line-height: 1.6;
          color: var(--text-secondary);
          margin: 0;
          white-space: pre-wrap;
          word-wrap: break-word;
        }
      `}</style>
    </div>
  );
}

function ChevronDownIcon() {
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
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

function ChevronUpIcon() {
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
      <polyline points="18 15 12 9 6 15" />
    </svg>
  );
}

function CopyIcon() {
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
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  );
}

function CheckIcon() {
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
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}
