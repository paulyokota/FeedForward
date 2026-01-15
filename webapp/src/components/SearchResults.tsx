"use client";

import { useCallback } from "react";
import type { SearchResult, ResearchSourceType } from "@/lib/types";
import { SOURCE_TYPE_CONFIG } from "@/lib/types";

interface SearchResultsProps {
  results: SearchResult[];
  isLoading?: boolean;
  query: string;
  onSimilar: (result: SearchResult) => void;
}

function SourceBadge({ sourceType }: { sourceType: ResearchSourceType }) {
  const config = SOURCE_TYPE_CONFIG[sourceType];

  return (
    <span
      className="source-badge"
      style={{
        backgroundColor: config.bgColor,
        color: config.color,
      }}
    >
      {config.label}
    </span>
  );
}

function SimilarityScore({ score }: { score: number }) {
  const percentage = Math.round(score * 100);
  return (
    <span className="similarity-score" title={`${percentage}% match`}>
      {percentage}%
    </span>
  );
}

function ResultCard({
  result,
  onSimilar,
  index,
}: {
  result: SearchResult;
  onSimilar: (result: SearchResult) => void;
  index: number;
}) {
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        // Open external link
        window.open(result.url, "_blank", "noopener,noreferrer");
      }
    },
    [result.url],
  );

  const handleSimilarClick = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      onSimilar(result);
    },
    [result, onSimilar],
  );

  return (
    <article
      className="result-card animate-fade-in"
      style={{ animationDelay: `${index * 40}ms` }}
      tabIndex={0}
      onKeyDown={handleKeyDown}
      aria-label={`Search result: ${result.title}`}
    >
      <div className="result-header">
        <SourceBadge sourceType={result.source_type} />
        <SimilarityScore score={result.similarity} />
      </div>

      <h3 className="result-title">{result.title}</h3>

      <p className="result-snippet">{result.snippet}</p>

      <div className="result-actions">
        <a
          href={result.url}
          target="_blank"
          rel="noopener noreferrer"
          className="action-link"
          onClick={(e) => e.stopPropagation()}
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
          Open
        </a>

        <button
          className="action-btn"
          onClick={handleSimilarClick}
          aria-label={`Find similar to ${result.title}`}
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <circle cx="12" cy="12" r="10" />
            <path d="M8 12h8" />
            <path d="M12 8v8" />
          </svg>
          More like this
        </button>
      </div>

      <style jsx>{`
        .result-card {
          padding: 20px;
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 16%),
            hsl(0, 0%, 12%)
          );
          border: 1px solid var(--border-subtle);
          border-radius: var(--radius-lg);
          box-shadow: var(--shadow-sm);
          transition: all 0.2s ease;
          cursor: pointer;
          opacity: 0;
          animation: fadeIn 0.25s ease-out forwards;
        }

        :global([data-theme="light"]) .result-card {
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 100%),
            hsl(0, 0%, 97%)
          );
        }

        .result-card:hover,
        .result-card:focus-visible {
          transform: translateY(-2px);
          box-shadow: var(--shadow-md);
          border-color: var(--border-default);
        }

        .result-card:focus-visible {
          outline: 2px solid var(--accent-blue);
          outline-offset: 2px;
        }

        .result-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 12px;
        }

        .source-badge {
          display: inline-flex;
          align-items: center;
          padding: 4px 10px;
          border-radius: var(--radius-full);
          font-size: 11px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.02em;
        }

        .similarity-score {
          font-size: 12px;
          font-weight: 600;
          color: var(--accent-green);
          background: var(--accent-green-dim);
          padding: 4px 8px;
          border-radius: var(--radius-sm);
        }

        .result-title {
          font-size: 16px;
          font-weight: 600;
          color: var(--text-primary);
          margin: 0 0 8px 0;
          line-height: 1.4;
        }

        .result-snippet {
          font-size: 14px;
          color: var(--text-secondary);
          line-height: 1.6;
          margin: 0 0 16px 0;
          display: -webkit-box;
          -webkit-line-clamp: 3;
          -webkit-box-orient: vertical;
          overflow: hidden;
        }

        .result-actions {
          display: flex;
          gap: 12px;
          flex-wrap: wrap;
        }

        .action-link,
        .action-btn {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 8px 14px;
          background: var(--bg-elevated);
          border: 1px solid var(--border-default);
          border-radius: var(--radius-md);
          color: var(--text-secondary);
          font-size: 13px;
          font-weight: 500;
          text-decoration: none;
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .action-link:hover,
        .action-btn:hover {
          background: var(--bg-hover);
          color: var(--text-primary);
          border-color: var(--border-strong);
        }

        .action-link:focus-visible,
        .action-btn:focus-visible {
          outline: 2px solid var(--accent-blue);
          outline-offset: 2px;
        }

        @keyframes fadeIn {
          from {
            opacity: 0;
            transform: translateY(6px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
      `}</style>
    </article>
  );
}

export function SearchResults({
  results,
  isLoading,
  query,
  onSimilar,
}: SearchResultsProps) {
  if (isLoading) {
    return (
      <div className="results-loading">
        <div className="loading-spinner" />
        <span>Searching...</span>

        <style jsx>{`
          .results-loading {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 60px 20px;
            gap: 16px;
            color: var(--text-secondary);
          }

          .loading-spinner {
            width: 28px;
            height: 28px;
            border: 3px solid var(--border-default);
            border-top-color: var(--accent-blue);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
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

  if (!query) {
    return (
      <div className="results-empty">
        <svg
          width="48"
          height="48"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        >
          <circle cx="11" cy="11" r="8" />
          <line x1="21" y1="21" x2="16.65" y2="16.65" />
        </svg>
        <h3>Search Research</h3>
        <p>
          Search across Coda research documents and Intercom support
          conversations to find relevant insights.
        </p>

        <style jsx>{`
          .results-empty {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 80px 20px;
            text-align: center;
            color: var(--text-tertiary);
          }

          .results-empty svg {
            margin-bottom: 16px;
            opacity: 0.5;
          }

          .results-empty h3 {
            font-size: 18px;
            font-weight: 600;
            color: var(--text-secondary);
            margin: 0 0 8px 0;
          }

          .results-empty p {
            font-size: 14px;
            max-width: 400px;
            line-height: 1.6;
            margin: 0;
          }
        `}</style>
      </div>
    );
  }

  if (results.length === 0) {
    return (
      <div className="results-empty">
        <svg
          width="48"
          height="48"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        >
          <circle cx="12" cy="12" r="10" />
          <line x1="15" y1="9" x2="9" y2="15" />
          <line x1="9" y1="9" x2="15" y2="15" />
        </svg>
        <h3>No results found</h3>
        <p>
          No research content matched your search for &quot;{query}&quot;. Try
          different keywords or broaden your filters.
        </p>

        <style jsx>{`
          .results-empty {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 80px 20px;
            text-align: center;
            color: var(--text-tertiary);
          }

          .results-empty svg {
            margin-bottom: 16px;
            opacity: 0.5;
          }

          .results-empty h3 {
            font-size: 18px;
            font-weight: 600;
            color: var(--text-secondary);
            margin: 0 0 8px 0;
          }

          .results-empty p {
            font-size: 14px;
            max-width: 400px;
            line-height: 1.6;
            margin: 0;
          }
        `}</style>
      </div>
    );
  }

  return (
    <div className="search-results">
      <div className="results-header">
        <span className="results-count">
          {results.length} result{results.length !== 1 ? "s" : ""} for &quot;
          {query}&quot;
        </span>
      </div>

      <div className="results-grid">
        {results.map((result, index) => (
          <ResultCard
            key={result.id}
            result={result}
            onSimilar={onSimilar}
            index={index}
          />
        ))}
      </div>

      <style jsx>{`
        .search-results {
          width: 100%;
        }

        .results-header {
          margin-bottom: 20px;
        }

        .results-count {
          font-size: 14px;
          color: var(--text-tertiary);
        }

        .results-grid {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }
      `}</style>
    </div>
  );
}
