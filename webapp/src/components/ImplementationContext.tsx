"use client";

import { useState } from "react";
import type { CodeContext } from "@/lib/types";

interface ImplementationContextProps {
  codeContext: CodeContext | null;
}

/**
 * Implementation Context Section
 *
 * Displays code-area pointers from classification-guided exploration.
 * Shows relevant files and code snippets when available.
 * Shows pending state when code context is empty.
 */
export function ImplementationContext({
  codeContext,
}: ImplementationContextProps) {
  const [copiedPath, setCopiedPath] = useState<string | null>(null);

  const handleCopyPath = async (path: string, lineStart?: number | null) => {
    const fullPath = lineStart ? `${path}:${lineStart}` : path;
    try {
      await navigator.clipboard.writeText(fullPath);
      setCopiedPath(fullPath);
      setTimeout(() => setCopiedPath(null), 2000);
    } catch (err) {
      console.error("Failed to copy path:", err);
    }
  };

  // Check if we have meaningful code context
  const hasContext =
    codeContext &&
    codeContext.success &&
    (codeContext.relevant_files.length > 0 ||
      codeContext.code_snippets.length > 0);

  return (
    <section className="implementation-context">
      <div className="section-header">
        <h2 className="section-title">Implementation Context</h2>
        {hasContext && codeContext?.classification && (
          <span
            className={`confidence-badge confidence-${codeContext.classification.confidence}`}
          >
            {codeContext.classification.confidence}
          </span>
        )}
      </div>

      {!hasContext ? (
        <div className="pending-state">
          <div className="pending-icon">
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
            </svg>
          </div>
          <p className="pending-text">Implementation context pending</p>
          <p className="pending-subtext">
            Code area pointers will appear here once the story is processed
            through the classification pipeline.
          </p>
        </div>
      ) : (
        <div className="context-content">
          {/* Classification Summary */}
          {codeContext?.classification && (
            <div className="classification-summary">
              <div className="classification-category">
                <span className="label">Category:</span>
                <span className="value">
                  {codeContext.classification.category}
                </span>
              </div>
              {codeContext.classification.reasoning && (
                <p className="classification-reasoning">
                  {codeContext.classification.reasoning}
                </p>
              )}
              {codeContext.classification.keywords_matched.length > 0 && (
                <div className="keywords">
                  {codeContext.classification.keywords_matched.map(
                    (keyword) => (
                      <span key={keyword} className="keyword-tag">
                        {keyword}
                      </span>
                    ),
                  )}
                </div>
              )}
            </div>
          )}

          {/* Relevant Files */}
          {codeContext?.relevant_files &&
            codeContext.relevant_files.length > 0 && (
              <div className="relevant-files">
                <h3 className="subsection-title">Relevant Files</h3>
                <ul className="file-list">
                  {codeContext.relevant_files.map((file, idx) => (
                    <li key={`${file.path}-${idx}`} className="file-item">
                      <div className="file-path-row">
                        <code className="file-path">
                          {file.path}
                          {file.line_start && (
                            <span className="line-range">
                              :{file.line_start}
                              {file.line_end &&
                                file.line_end !== file.line_start && (
                                  <>-{file.line_end}</>
                                )}
                            </span>
                          )}
                        </code>
                        <button
                          className="copy-btn"
                          onClick={() =>
                            handleCopyPath(file.path, file.line_start)
                          }
                          title="Copy path"
                        >
                          {copiedPath ===
                          (file.line_start
                            ? `${file.path}:${file.line_start}`
                            : file.path) ? (
                            <svg
                              width="14"
                              height="14"
                              viewBox="0 0 24 24"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="2"
                            >
                              <path d="M20 6L9 17l-5-5" />
                            </svg>
                          ) : (
                            <svg
                              width="14"
                              height="14"
                              viewBox="0 0 24 24"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="2"
                            >
                              <rect
                                x="9"
                                y="9"
                                width="13"
                                height="13"
                                rx="2"
                                ry="2"
                              />
                              <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
                            </svg>
                          )}
                        </button>
                      </div>
                      {file.relevance && (
                        <p className="file-relevance">{file.relevance}</p>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}

          {/* Code Snippets */}
          {codeContext?.code_snippets &&
            codeContext.code_snippets.length > 0 && (
              <div className="code-snippets">
                <h3 className="subsection-title">Code Snippets</h3>
                {codeContext.code_snippets.map((snippet, idx) => (
                  <div
                    key={`${snippet.file_path}-${idx}`}
                    className="snippet-card"
                  >
                    <div className="snippet-header">
                      <code className="snippet-path">
                        {snippet.file_path}:{snippet.line_start}-
                        {snippet.line_end}
                      </code>
                      <button
                        className="copy-btn"
                        onClick={() =>
                          handleCopyPath(snippet.file_path, snippet.line_start)
                        }
                        title="Copy path"
                      >
                        {copiedPath ===
                        `${snippet.file_path}:${snippet.line_start}` ? (
                          <svg
                            width="14"
                            height="14"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                          >
                            <path d="M20 6L9 17l-5-5" />
                          </svg>
                        ) : (
                          <svg
                            width="14"
                            height="14"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                          >
                            <rect
                              x="9"
                              y="9"
                              width="13"
                              height="13"
                              rx="2"
                              ry="2"
                            />
                            <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
                          </svg>
                        )}
                      </button>
                    </div>
                    {snippet.context && (
                      <p className="snippet-context">{snippet.context}</p>
                    )}
                    <pre className="snippet-code">
                      <code className={`language-${snippet.language}`}>
                        {snippet.content}
                      </code>
                    </pre>
                  </div>
                ))}
              </div>
            )}

          {/* Exploration Timing */}
          {codeContext?.explored_at && (
            <div className="exploration-meta">
              <span className="meta-item">
                Explored{" "}
                {new Date(codeContext.explored_at).toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                  year: "numeric",
                })}
              </span>
              {codeContext.exploration_duration_ms > 0 && (
                <span className="meta-item">
                  {codeContext.exploration_duration_ms}ms
                </span>
              )}
            </div>
          )}
        </div>
      )}

      <style jsx>{`
        .implementation-context {
          margin-bottom: 32px;
        }

        .section-header {
          display: flex;
          align-items: center;
          gap: 10px;
          margin-bottom: 16px;
        }

        .section-title {
          font-size: 14px;
          font-weight: 600;
          color: var(--text-primary);
          margin: 0;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .confidence-badge {
          font-size: 11px;
          font-weight: 500;
          padding: 2px 8px;
          border-radius: 10px;
          text-transform: capitalize;
        }

        .confidence-high {
          color: var(--accent-green);
          background: var(--accent-green-dim);
        }

        .confidence-medium {
          color: var(--accent-amber);
          background: var(--accent-amber-dim);
        }

        .confidence-low {
          color: var(--text-tertiary);
          background: var(--bg-elevated);
        }

        /* Pending State */
        .pending-state {
          padding: 32px 24px;
          text-align: center;
          border: 1px dashed var(--border-subtle);
          border-radius: var(--radius-md);
          background: var(--bg-surface);
        }

        .pending-icon {
          color: var(--text-muted);
          margin-bottom: 12px;
        }

        .pending-text {
          font-size: 14px;
          font-weight: 500;
          color: var(--text-secondary);
          margin: 0 0 6px 0;
        }

        .pending-subtext {
          font-size: 13px;
          color: var(--text-muted);
          margin: 0;
          max-width: 400px;
          margin-left: auto;
          margin-right: auto;
        }

        /* Context Content */
        .context-content {
          display: flex;
          flex-direction: column;
          gap: 20px;
        }

        /* Classification Summary */
        .classification-summary {
          padding: 16px;
          background: var(--bg-surface);
          border: 1px solid var(--border-subtle);
          border-radius: var(--radius-md);
        }

        .classification-category {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 8px;
        }

        .classification-category .label {
          font-size: 12px;
          color: var(--text-muted);
        }

        .classification-category .value {
          font-size: 13px;
          font-weight: 500;
          color: var(--text-primary);
        }

        .classification-reasoning {
          font-size: 13px;
          color: var(--text-secondary);
          line-height: 1.5;
          margin: 0 0 10px 0;
        }

        .keywords {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
        }

        .keyword-tag {
          font-size: 11px;
          color: var(--accent-blue);
          background: var(--accent-blue-dim);
          padding: 3px 8px;
          border-radius: 4px;
          font-family: var(--font-mono);
        }

        /* Relevant Files */
        .subsection-title {
          font-size: 13px;
          font-weight: 600;
          color: var(--text-secondary);
          margin: 0 0 12px 0;
        }

        .file-list {
          list-style: none;
          padding: 0;
          margin: 0;
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        .file-item {
          padding: 10px 12px;
          background: var(--bg-surface);
          border: 1px solid var(--border-subtle);
          border-radius: var(--radius-sm);
        }

        .file-path-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 8px;
        }

        .file-path {
          font-size: 12px;
          font-family: var(--font-mono);
          color: var(--text-primary);
          word-break: break-all;
        }

        .line-range {
          color: var(--accent-blue);
        }

        .copy-btn {
          flex-shrink: 0;
          padding: 4px;
          background: none;
          border: none;
          color: var(--text-muted);
          cursor: pointer;
          border-radius: var(--radius-sm);
          transition: all 0.15s ease;
        }

        .copy-btn:hover {
          color: var(--text-primary);
          background: var(--bg-elevated);
        }

        .file-relevance {
          font-size: 12px;
          color: var(--text-tertiary);
          margin: 6px 0 0 0;
          line-height: 1.4;
        }

        /* Code Snippets */
        .snippet-card {
          background: var(--bg-surface);
          border: 1px solid var(--border-subtle);
          border-radius: var(--radius-md);
          overflow: hidden;
        }

        .snippet-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 10px 12px;
          background: var(--bg-elevated);
          border-bottom: 1px solid var(--border-subtle);
        }

        .snippet-path {
          font-size: 11px;
          font-family: var(--font-mono);
          color: var(--text-secondary);
        }

        .snippet-context {
          font-size: 12px;
          color: var(--text-secondary);
          padding: 10px 12px;
          margin: 0;
          border-bottom: 1px solid var(--border-subtle);
          background: var(--bg-surface);
        }

        .snippet-code {
          margin: 0;
          padding: 12px;
          background: var(--bg-void);
          overflow-x: auto;
          font-size: 12px;
          line-height: 1.5;
        }

        .snippet-code code {
          font-family: var(--font-mono);
          color: var(--text-primary);
        }

        /* Exploration Meta */
        .exploration-meta {
          display: flex;
          gap: 16px;
          font-size: 11px;
          color: var(--text-muted);
        }

        .meta-item {
          display: flex;
          align-items: center;
          gap: 4px;
        }
      `}</style>
    </section>
  );
}
