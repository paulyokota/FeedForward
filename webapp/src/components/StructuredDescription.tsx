"use client";

import React, { useState, useMemo } from "react";
import storySectionsConfig from "@/config/story-sections.json";

interface StructuredDescriptionProps {
  description: string;
}

interface SectionConfig {
  parent: string;
  collapsed: boolean;
  render: string;
  aliases?: string[];
}

interface ParsedSection {
  title: string;
  normalizedTitle: string;
  content: string;
  config: SectionConfig;
  parentSection: "human_facing" | "ai_agent";
}

// Build lookup map from schema (including aliases)
const sectionConfigMap = new Map<string, SectionConfig>();
for (const [name, config] of Object.entries(storySectionsConfig.sections)) {
  const cfg = config as SectionConfig;
  sectionConfigMap.set(name.toLowerCase(), cfg);
  if (cfg.aliases) {
    for (const alias of cfg.aliases) {
      sectionConfigMap.set(alias.toLowerCase(), cfg);
    }
  }
}

const defaultConfig: SectionConfig =
  storySectionsConfig.unknown_section_defaults as SectionConfig;

/**
 * Look up section config, falling back to defaults for unknown sections
 */
function getSectionConfig(title: string): SectionConfig {
  return sectionConfigMap.get(title.toLowerCase()) || defaultConfig;
}

/**
 * Parse description into sections.
 * Parses ANY ## header, looks up config from schema.
 */
function parseDescription(description: string): ParsedSection[] {
  const parts: Array<{
    title: string;
    startIndex: number;
    contentIndex: number;
  }> = [];

  // Find all ## headers (parse any header, not just known ones)
  const markdownHeaderPattern = /(?:^|\n)##\s+([^\n]+)/g;
  let match;
  while ((match = markdownHeaderPattern.exec(description)) !== null) {
    const title = match[1].trim();
    parts.push({
      title,
      startIndex: match.index,
      contentIndex: match.index + match[0].length,
    });
  }

  // Sort by position
  parts.sort((a, b) => a.startIndex - b.startIndex);

  if (parts.length === 0) {
    return [];
  }

  // Detect if we're in Section 2 (AI Agent) based on marker
  let inAiAgentSection = false;
  const section2Marker =
    storySectionsConfig.parents.ai_agent.marker.toLowerCase();

  const sections: ParsedSection[] = parts.map((part, idx) => {
    const nextStartIndex =
      idx < parts.length - 1 ? parts[idx + 1].startIndex : description.length;
    const content = description
      .substring(part.contentIndex, nextStartIndex)
      .trim();

    // Check if this header marks start of AI Agent section
    if (part.title.toLowerCase().includes(section2Marker.toLowerCase())) {
      inAiAgentSection = true;
    }

    const config = getSectionConfig(part.title);

    // Determine parent: use config if known section, otherwise infer from position
    let parentSection: "human_facing" | "ai_agent";
    if (config !== defaultConfig) {
      parentSection = config.parent as "human_facing" | "ai_agent";
    } else {
      parentSection = inAiAgentSection ? "ai_agent" : "human_facing";
    }

    return {
      title: part.title,
      normalizedTitle: part.title.toLowerCase(),
      content,
      config,
      parentSection,
    };
  });

  // Filter out empty sections and section markers themselves
  return sections.filter((s) => {
    if (s.content.length === 0) return false;
    // Skip "SECTION 1:" and "SECTION 2:" marker headers
    if (
      s.title.toLowerCase().startsWith("section 1") ||
      s.title.toLowerCase().startsWith("section 2")
    ) {
      return false;
    }
    return true;
  });
}

/**
 * Render content with bold text support
 */
function renderTextWithBold(text: string): React.ReactNode {
  const boldPattern = /\*\*([^*]+)\*\*/g;
  const parts = text.split(boldPattern);
  if (parts.length === 1) return text;
  return parts.map((part, i) =>
    i % 2 === 1 ? <strong key={i}>{part}</strong> : part,
  );
}

/**
 * Render a checkbox item (supports both markdown and unicode formats)
 */
function CheckboxItem({ line, index }: { line: string; index: number }) {
  const trimmed = line.trim();

  // Markdown checkbox: - [ ] or - [x]
  const mdMatch = trimmed.match(/^-\s*\[([ xX])\]\s*(.*)$/);
  if (mdMatch) {
    const isChecked = mdMatch[1].toLowerCase() === "x";
    const text = mdMatch[2];
    return (
      <div key={index} className="checkbox-item">
        <span className={`checkbox ${isChecked ? "checked" : ""}`}>
          {isChecked ? "✓" : "○"}
        </span>
        <span className={isChecked ? "checked-text" : ""}>
          {renderTextWithBold(text)}
        </span>
      </div>
    );
  }

  // Unicode checkbox: ✓, ✗, ○ at start of line
  const unicodeMatch = trimmed.match(/^([✓✗○])\s*(.*)$/);
  if (unicodeMatch) {
    const marker = unicodeMatch[1];
    const text = unicodeMatch[2];
    const isChecked = marker === "✓";
    const isFailed = marker === "✗";
    return (
      <div key={index} className="checkbox-item">
        <span
          className={`checkbox ${isChecked ? "checked" : ""} ${isFailed ? "failed" : ""}`}
        >
          {marker}
        </span>
        <span className={isChecked ? "checked-text" : ""}>
          {renderTextWithBold(text)}
        </span>
      </div>
    );
  }

  return null;
}

/**
 * Render section content based on render type
 * Note: isExpanded here is for content truncation, NOT schema-controlled collapse
 */
function SectionContent({ section }: { section: ParsedSection }) {
  const [isExpanded, setIsExpanded] = useState(false);

  const lines = section.content.split("\n").filter((line) => line.trim());
  const LONG_THRESHOLD = 5;
  const isLong = lines.length > LONG_THRESHOLD;
  const shouldTruncate = isLong && !isExpanded;
  const displayLines = shouldTruncate ? lines.slice(0, LONG_THRESHOLD) : lines;
  const remainingCount = lines.length - LONG_THRESHOLD;

  const renderContent = () => {
    const elements: React.ReactElement[] = [];
    let bulletGroup: React.ReactNode[] = [];

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

      // Skip ### sub-headers but show them as bold text
      if (trimmed.startsWith("### ")) {
        flushBullets();
        elements.push(
          <p key={idx} className="content-line sub-header">
            <strong>{trimmed.replace("### ", "")}</strong>
          </p>,
        );
        return;
      }

      // Check for checkbox items (markdown or unicode)
      const isCheckbox =
        /^-\s*\[([ xX])\]/.test(trimmed) || /^[✓✗○]/.test(trimmed);

      if (isCheckbox) {
        flushBullets();
        const checkboxEl = (
          <CheckboxItem key={idx} line={trimmed} index={idx} />
        );
        if (checkboxEl) elements.push(checkboxEl);
        return;
      }

      // Check for numbered list
      const numberedMatch = trimmed.match(/^(\d+)\.\s+(.*)$/);
      if (numberedMatch) {
        flushBullets();
        elements.push(
          <p key={idx} className="content-line numbered-item">
            <span className="number">{numberedMatch[1]}.</span>
            {renderTextWithBold(numberedMatch[2])}
          </p>,
        );
        return;
      }

      // Check for bullet points (but not bold markers like **text**)
      const isBullet =
        trimmed.startsWith("- ") ||
        trimmed.startsWith("-\t") ||
        trimmed.startsWith("• ") ||
        (trimmed.startsWith("* ") && !trimmed.startsWith("**"));

      if (isBullet) {
        const bulletText = trimmed.replace(/^[-•*]\s+/, "");
        bulletGroup.push(renderTextWithBold(bulletText));
        return;
      }

      // Check for table row
      if (trimmed.startsWith("|") && trimmed.endsWith("|")) {
        flushBullets();
        // Skip separator rows
        if (/^\|[\s\-:|]+\|$/.test(trimmed)) return;

        const cells = trimmed.split("|").filter((c) => c.trim());
        elements.push(
          <div key={idx} className="table-row">
            {cells.map((cell, i) => (
              <span key={i} className="table-cell">
                {renderTextWithBold(cell.trim())}
              </span>
            ))}
          </div>,
        );
        return;
      }

      // Regular paragraph
      flushBullets();
      if (trimmed) {
        elements.push(
          <p key={idx} className="content-line">
            {renderTextWithBold(trimmed)}
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

      {isLong && (
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

        .content-line.sub-header {
          margin-top: 12px;
          color: var(--text-primary);
        }

        .content-line.numbered-item {
          display: flex;
          gap: 8px;
        }

        .content-line.numbered-item .number {
          color: var(--text-tertiary);
          min-width: 20px;
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

        .table-row {
          display: flex;
          gap: 16px;
          padding: 4px 0;
          border-bottom: 1px solid var(--border-subtle);
        }

        .table-row:first-child {
          font-weight: 600;
          color: var(--text-primary);
        }

        .table-cell {
          flex: 1;
          min-width: 0;
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

/**
 * Collapsible section group (for AI Agent section)
 */
function SectionGroup({
  title,
  sections,
  defaultCollapsed,
}: {
  title: string;
  sections: ParsedSection[];
  defaultCollapsed: boolean;
}) {
  const [isCollapsed, setIsCollapsed] = useState(defaultCollapsed);

  if (sections.length === 0) return null;

  return (
    <div className="section-group">
      <button
        type="button"
        className="group-header"
        onClick={() => setIsCollapsed(!isCollapsed)}
      >
        {isCollapsed ? <ChevronRightIcon /> : <ChevronDownIcon />}
        <span className="group-title">{title}</span>
        <span className="group-count">{sections.length} sections</span>
      </button>

      {!isCollapsed && (
        <div className="group-content">
          {sections.map((section, idx) => (
            <div key={idx} className="section">
              <h3 className="section-title">{section.title}</h3>
              <SectionContent section={section} />
            </div>
          ))}
        </div>
      )}

      <style jsx>{`
        .section-group {
          margin-bottom: 20px;
          border: 1px solid var(--border-default);
          border-radius: var(--radius-md);
          overflow: hidden;
        }

        .group-header {
          display: flex;
          align-items: center;
          gap: 8px;
          width: 100%;
          padding: 12px 16px;
          background: var(--bg-elevated);
          border: none;
          cursor: pointer;
          text-align: left;
          transition: background 0.15s ease;
        }

        .group-header:hover {
          background: var(--bg-hover);
        }

        .group-title {
          font-size: 14px;
          font-weight: 600;
          color: var(--text-primary);
        }

        .group-count {
          font-size: 12px;
          color: var(--text-tertiary);
          margin-left: auto;
        }

        .group-content {
          padding: 16px;
          border-top: 1px solid var(--border-default);
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
          font-size: 15px;
          font-weight: 600;
          color: var(--text-primary);
          margin: 0 0 12px 0;
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

  const sections = useMemo(() => parseDescription(description), [description]);

  // Group sections by parent
  const humanSections = sections.filter(
    (s) => s.parentSection === "human_facing",
  );
  const aiSections = sections.filter((s) => s.parentSection === "ai_agent");

  const shouldUseStructured = sections.length > 0;

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
          {/* Human-facing sections (expanded) */}
          {humanSections.map((section, idx) => (
            <div key={idx} className="section">
              <h3 className="section-title">{section.title}</h3>
              <SectionContent section={section} />
            </div>
          ))}

          {/* AI Agent sections (collapsed by default) */}
          {aiSections.length > 0 && (
            <SectionGroup
              title={storySectionsConfig.parents.ai_agent.display}
              sections={aiSections}
              defaultCollapsed={storySectionsConfig.parents.ai_agent.collapsed}
            />
          )}
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

      {/* Global styles for checkbox items */}
      <style jsx global>{`
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

        .checkbox.failed {
          background: var(--status-error, #dc2626);
          border-color: var(--status-error, #dc2626);
          color: white;
        }

        .checked-text {
          text-decoration: line-through;
          opacity: 0.7;
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

function ChevronRightIcon() {
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
      <polyline points="9 18 15 12 9 6" />
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
