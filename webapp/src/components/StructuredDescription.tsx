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

/**
 * Parse description text into structured sections.
 * Looks for markdown-style headers (e.g., **Summary**, **Impact**, **Evidence**).
 */
function parseDescription(description: string): Section[] | null {
  // Split by markdown bold headers
  const sectionPattern = /\*\*([^*]+)\*\*/g;
  const parts: Array<{ title: string; index: number }> = [];

  let match;
  while ((match = sectionPattern.exec(description)) !== null) {
    parts.push({
      title: match[1].trim(),
      index: match.index + match[0].length,
    });
  }

  if (parts.length === 0) {
    return null; // No structured sections found
  }

  const sections: Section[] = parts.map((part, idx) => {
    const nextIndex =
      idx < parts.length - 1
        ? parts[idx + 1].index - parts[idx + 1].title.length - 4
        : description.length;
    const content = description.substring(part.index, nextIndex).trim();

    // Consider content "long" if it has more than 3 lines
    const lineCount = content.split("\n").filter((line) => line.trim()).length;
    const isLong = lineCount > 3;

    return { title: part.title, content, isLong };
  });

  return sections;
}

/**
 * Render a single section with progressive disclosure for long content.
 */
function SectionContent({ section }: { section: Section }) {
  const [isExpanded, setIsExpanded] = useState(false);

  // Split into lines for progressive disclosure
  const lines = section.content.split("\n").filter((line) => line.trim());
  const shouldTruncate = section.isLong && !isExpanded;
  const displayLines = shouldTruncate ? lines.slice(0, 3) : lines;
  const remainingCount = lines.length - 3;

  return (
    <div className="section-content">
      <div className="content-text">
        {displayLines.map((line, idx) => {
          const trimmed = line.trim();
          // Detect if line is a bullet point
          const isBullet = trimmed.startsWith("-") || trimmed.startsWith("•");

          if (isBullet) {
            return (
              <li key={idx} className="bullet-item">
                {trimmed.substring(1).trim()}
              </li>
            );
          }

          return (
            <p key={idx} className="content-line">
              {trimmed}
            </p>
          );
        })}
      </div>

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

        .bullet-item {
          margin: 4px 0 4px 20px;
          color: var(--text-secondary);
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
  const [copySuccess, setCopySuccess] = useState(false);

  const sections = parseDescription(description);
  const shouldUseStructured = sections !== null && sections.length > 0;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(description);
      setCopySuccess(true);
      setTimeout(() => setCopySuccess(false), 2000);
    } catch (err) {
      console.error("Failed to copy:", err);
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
          className="copy-btn"
          onClick={handleCopy}
          title="Copy raw description"
        >
          {copySuccess ? (
            <>
              <CheckIcon />
              Copied!
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
