"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import type { SuggestedEvidence as SuggestedEvidenceType } from "@/lib/types";
import { SOURCE_TYPE_CONFIG } from "@/lib/types";

interface SuggestedEvidenceProps {
  storyId: string;
  onEvidenceAccepted?: () => void;
}

export function SuggestedEvidence({
  storyId,
  onEvidenceAccepted,
}: SuggestedEvidenceProps) {
  const [suggestions, setSuggestions] = useState<SuggestedEvidenceType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);

  const fetchSuggestions = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.research.getSuggestedEvidence(storyId);
      // Show both suggested and accepted items (rejected are filtered server-side)
      setSuggestions(data);
    } catch (err) {
      // API not ready yet - this is expected during development
      console.warn("Failed to fetch suggested evidence:", err);
      setError(null); // Don't show error, just show empty state
      setSuggestions([]);
    } finally {
      setLoading(false);
    }
  }, [storyId]);

  useEffect(() => {
    fetchSuggestions();
  }, [fetchSuggestions]);

  const handleAccept = useCallback(
    async (evidenceId: string) => {
      setActionInProgress(evidenceId);
      try {
        await api.research.acceptEvidence(storyId, evidenceId);
        // Update status locally to "accepted"
        setSuggestions((prev) =>
          prev.map((s) =>
            s.id === evidenceId ? { ...s, status: "accepted" as const } : s,
          ),
        );
        onEvidenceAccepted?.();
      } catch (err) {
        console.error("Failed to accept evidence:", err);
      } finally {
        setActionInProgress(null);
      }
    },
    [storyId, onEvidenceAccepted],
  );

  const handleReject = useCallback(
    async (evidenceId: string) => {
      setActionInProgress(evidenceId);
      try {
        await api.research.rejectEvidence(storyId, evidenceId);
        // Remove rejected item from UI
        setSuggestions((prev) => prev.filter((s) => s.id !== evidenceId));
      } catch (err) {
        console.error("Failed to reject evidence:", err);
      } finally {
        setActionInProgress(null);
      }
    },
    [storyId],
  );

  if (loading) {
    return (
      <div className="suggested-loading">
        <div className="loading-dots">
          <span />
          <span />
          <span />
        </div>
        <span>Finding related research...</span>

        <style jsx>{`
          .suggested-loading {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 20px;
            color: var(--text-tertiary);
            font-size: 13px;
          }

          .loading-dots {
            display: flex;
            gap: 4px;
          }

          .loading-dots span {
            width: 6px;
            height: 6px;
            background: var(--accent-blue);
            border-radius: 50%;
            animation: pulse 1.4s infinite ease-in-out both;
          }

          .loading-dots span:nth-child(1) {
            animation-delay: -0.32s;
          }

          .loading-dots span:nth-child(2) {
            animation-delay: -0.16s;
          }

          @keyframes pulse {
            0%,
            80%,
            100% {
              transform: scale(0);
            }
            40% {
              transform: scale(1);
            }
          }
        `}</style>
      </div>
    );
  }

  if (error) {
    return null; // Silent failure - feature not critical
  }

  if (suggestions.length === 0) {
    return null; // Don't show section if no suggestions
  }

  return (
    <div className="suggested-evidence">
      <div className="section-header">
        <div className="header-content">
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
          </svg>
          <h3 className="section-title">Suggested Research</h3>
          <span className="suggestion-count">{suggestions.length}</span>
        </div>
        <p className="section-subtitle">
          Research that may support this story based on content similarity
        </p>
      </div>

      <div className="suggestions-list">
        {suggestions.map((suggestion, index) => {
          const config = SOURCE_TYPE_CONFIG[suggestion.source_type];
          const isProcessing = actionInProgress === suggestion.id;
          const isAccepted = suggestion.status === "accepted";

          return (
            <div
              key={suggestion.id}
              className={`suggestion-card ${isProcessing ? "processing" : ""} ${isAccepted ? "accepted" : ""}`}
              style={{ animationDelay: `${index * 50}ms` }}
            >
              <div className="suggestion-header">
                <span
                  className="source-badge"
                  style={{
                    backgroundColor: config.bgColor,
                    color: config.color,
                  }}
                >
                  {config.label}
                </span>
                <span className="similarity-badge">
                  {Math.round(suggestion.similarity * 100)}% match
                </span>
                {isAccepted && (
                  <span className="status-badge accepted-badge">
                    <svg
                      width="12"
                      height="12"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                    Accepted
                  </span>
                )}
              </div>

              <h4 className="suggestion-title">{suggestion.title}</h4>
              <p className="suggestion-snippet">{suggestion.snippet}</p>

              <div className="suggestion-actions">
                {!isAccepted ? (
                  <>
                    <button
                      className="action-accept"
                      onClick={() => handleAccept(suggestion.id)}
                      disabled={isProcessing}
                      aria-label="Accept this evidence"
                    >
                      <svg
                        width="14"
                        height="14"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                      >
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                      Accept
                    </button>

                    <button
                      className="action-reject"
                      onClick={() => handleReject(suggestion.id)}
                      disabled={isProcessing}
                      aria-label="Reject this evidence"
                    >
                      <svg
                        width="14"
                        height="14"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                      >
                        <line x1="18" y1="6" x2="6" y2="18" />
                        <line x1="6" y1="6" x2="18" y2="18" />
                      </svg>
                      Reject
                    </button>
                  </>
                ) : (
                  <button
                    className="action-undo"
                    onClick={() => handleReject(suggestion.id)}
                    disabled={isProcessing}
                    aria-label="Undo acceptance"
                  >
                    <svg
                      width="14"
                      height="14"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
                      <path d="M3 3v5h5" />
                    </svg>
                    Undo
                  </button>
                )}

                <a
                  href={suggestion.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="action-view"
                >
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                  >
                    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                    <polyline points="15 3 21 3 21 9" />
                    <line x1="10" y1="14" x2="21" y2="3" />
                  </svg>
                  View
                </a>
              </div>
            </div>
          );
        })}
      </div>

      <style jsx>{`
        .suggested-evidence {
          margin-top: 24px;
        }

        .section-header {
          margin-bottom: 16px;
        }

        .header-content {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 4px;
          color: var(--accent-blue);
        }

        .section-title {
          font-size: 14px;
          font-weight: 600;
          color: var(--text-primary);
          margin: 0;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .suggestion-count {
          font-size: 12px;
          color: var(--text-tertiary);
          background: var(--bg-elevated);
          padding: 2px 8px;
          border-radius: 10px;
        }

        .section-subtitle {
          font-size: 13px;
          color: var(--text-tertiary);
          margin: 0;
        }

        .suggestions-list {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .suggestion-card {
          padding: 16px;
          background: var(--bg-surface);
          border: 1px solid var(--border-subtle);
          border-radius: var(--radius-md);
          opacity: 0;
          animation: fadeIn 0.25s ease-out forwards;
          transition: opacity 0.2s ease;
        }

        .suggestion-card.processing {
          opacity: 0.6;
          pointer-events: none;
        }

        .suggestion-header {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 10px;
        }

        .source-badge {
          display: inline-flex;
          align-items: center;
          padding: 3px 8px;
          border-radius: var(--radius-full);
          font-size: 10px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.02em;
        }

        .similarity-badge {
          font-size: 11px;
          font-weight: 600;
          color: var(--accent-green);
          background: var(--accent-green-dim);
          padding: 3px 8px;
          border-radius: var(--radius-sm);
        }

        .status-badge {
          display: inline-flex;
          align-items: center;
          gap: 4px;
          font-size: 11px;
          font-weight: 600;
          padding: 3px 8px;
          border-radius: var(--radius-sm);
        }

        .accepted-badge {
          color: var(--accent-green);
          background: var(--accent-green-dim);
        }

        .suggestion-card.accepted {
          border-color: var(--accent-green);
          background: hsla(160, 64%, 52%, 0.05);
        }

        .suggestion-title {
          font-size: 14px;
          font-weight: 600;
          color: var(--text-primary);
          margin: 0 0 6px 0;
          line-height: 1.4;
        }

        .suggestion-snippet {
          font-size: 13px;
          color: var(--text-secondary);
          line-height: 1.5;
          margin: 0 0 14px 0;
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
          overflow: hidden;
        }

        .suggestion-actions {
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
        }

        .action-accept,
        .action-reject,
        .action-view,
        .action-undo {
          display: inline-flex;
          align-items: center;
          gap: 5px;
          padding: 6px 12px;
          border-radius: var(--radius-md);
          font-size: 12px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.15s ease;
          text-decoration: none;
        }

        .action-accept {
          background: var(--accent-green-dim);
          border: 1px solid transparent;
          color: var(--accent-green);
        }

        .action-accept:hover:not(:disabled) {
          background: var(--accent-green);
          color: white;
        }

        .action-reject {
          background: var(--bg-elevated);
          border: 1px solid var(--border-default);
          color: var(--text-secondary);
        }

        .action-reject:hover:not(:disabled) {
          background: var(--accent-red-dim);
          color: var(--accent-red);
          border-color: var(--accent-red);
        }

        .action-view {
          background: var(--bg-elevated);
          border: 1px solid var(--border-default);
          color: var(--text-secondary);
        }

        .action-view:hover {
          background: var(--bg-hover);
          color: var(--text-primary);
        }

        .action-undo {
          background: var(--bg-elevated);
          border: 1px solid var(--border-default);
          color: var(--text-secondary);
        }

        .action-undo:hover:not(:disabled) {
          background: var(--accent-amber-dim, hsla(45, 93%, 47%, 0.15));
          color: var(--accent-amber, hsl(45, 93%, 47%));
          border-color: var(--accent-amber, hsl(45, 93%, 47%));
        }

        .action-accept:disabled,
        .action-reject:disabled,
        .action-undo:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .action-accept:focus-visible,
        .action-reject:focus-visible,
        .action-view:focus-visible,
        .action-undo:focus-visible {
          outline: 2px solid var(--accent-blue);
          outline-offset: 2px;
        }

        @keyframes fadeIn {
          from {
            opacity: 0;
            transform: translateY(4px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
      `}</style>
    </div>
  );
}
