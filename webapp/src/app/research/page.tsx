"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { SearchResult, ResearchSourceType } from "@/lib/types";
import { ResearchSearch } from "@/components/ResearchSearch";
import { SourceFilter, type FilterOption } from "@/components/SourceFilter";
import { SearchResults } from "@/components/SearchResults";
import { ThemeToggle } from "@/components/ThemeToggle";
import { FeedForwardLogo } from "@/components/FeedForwardLogo";
import Link from "next/link";

// Mock data for development before backend is ready
const MOCK_RESULTS: SearchResult[] = [
  {
    id: "1",
    source_type: "coda_page",
    source_id: "canvas_123",
    title: "User Research: Scheduling Pain Points",
    snippet:
      "Users consistently report frustration with the scheduling workflow. Many mention that finding available time slots takes too long and the interface is confusing when dealing with recurring events.",
    similarity: 0.92,
    url: "https://coda.io/d/research/scheduling",
    metadata: {},
  },
  {
    id: "2",
    source_type: "intercom",
    source_id: "conv_456",
    title: "Support: Calendar sync issues",
    snippet:
      "Customer reported that their Google Calendar events are not syncing properly. They mentioned having to manually refresh multiple times before changes appear.",
    similarity: 0.85,
    url: "https://app.intercom.com/conversations/456",
    metadata: {},
  },
  {
    id: "3",
    source_type: "coda_theme",
    source_id: "theme_789",
    title: "Theme: Notification Preferences",
    snippet:
      "Users want more granular control over notifications. Common requests include: ability to snooze, channel-specific settings, and quiet hours.",
    similarity: 0.78,
    url: "https://coda.io/d/themes/notifications",
    metadata: {},
  },
];

export default function ResearchPage() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [sourceFilter, setSourceFilter] = useState<FilterOption>("all");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [useMockData, setUseMockData] = useState(false);

  // Debounce search query
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQuery(query);
    }, 300);

    return () => clearTimeout(timer);
  }, [query]);

  // Perform search when debounced query or filter changes
  useEffect(() => {
    if (!debouncedQuery.trim()) {
      setResults([]);
      return;
    }

    const performSearch = async () => {
      setIsSearching(true);
      try {
        const sourceTypes: ResearchSourceType[] | undefined =
          sourceFilter === "all" ? undefined : [sourceFilter];

        const searchResults = await api.research.search(
          debouncedQuery,
          sourceTypes,
          20,
        );
        setResults(searchResults);
        setUseMockData(false);
      } catch (err) {
        // API not ready - use mock data for development
        console.warn("Search API not ready, using mock data:", err);
        let mockFiltered = MOCK_RESULTS.filter(
          (r) =>
            r.title.toLowerCase().includes(debouncedQuery.toLowerCase()) ||
            r.snippet.toLowerCase().includes(debouncedQuery.toLowerCase()),
        );
        if (sourceFilter !== "all") {
          mockFiltered = mockFiltered.filter(
            (r) => r.source_type === sourceFilter,
          );
        }
        setResults(mockFiltered.length > 0 ? mockFiltered : MOCK_RESULTS);
        setUseMockData(true);
      } finally {
        setIsSearching(false);
      }
    };

    performSearch();
  }, [debouncedQuery, sourceFilter]);

  const handleSimilar = useCallback(async (result: SearchResult) => {
    setIsSearching(true);
    try {
      const similarResults = await api.research.getSimilar(
        result.source_type,
        result.source_id,
        10,
      );
      setResults(similarResults);
      setQuery(`Similar to: ${result.title}`);
      setUseMockData(false);
    } catch (err) {
      // API not ready - show filtered mock data
      console.warn("Similar API not ready:", err);
      const mockSimilar = MOCK_RESULTS.filter((r) => r.id !== result.id);
      setResults(mockSimilar);
      setQuery(`Similar to: ${result.title}`);
      setUseMockData(true);
    } finally {
      setIsSearching(false);
    }
  }, []);

  const handleClearSearch = useCallback(() => {
    setQuery("");
    setResults([]);
    setUseMockData(false);
  }, []);

  return (
    <div className="research-page">
      {/* Header */}
      <header className="page-header">
        <nav className="header-left">
          <button className="logo-link" onClick={() => router.push("/")}>
            <FeedForwardLogo size="sm" />
          </button>
          <div className="header-divider" />
          <span className="page-title">Research</span>
        </nav>

        <div className="header-right">
          <Link href="/" className="nav-link">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <rect x="3" y="3" width="7" height="7" />
              <rect x="14" y="3" width="7" height="7" />
              <rect x="14" y="14" width="7" height="7" />
              <rect x="3" y="14" width="7" height="7" />
            </svg>
            Stories
          </Link>
          <Link href="/analytics" className="nav-link">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path d="M18 20V10" />
              <path d="M12 20V4" />
              <path d="M6 20v-6" />
            </svg>
            Analytics
          </Link>
          <ThemeToggle />
        </div>
      </header>

      {/* Main Content */}
      <main className="page-content">
        {/* Search Section */}
        <section className="search-section">
          <div className="search-container">
            <h1 className="search-heading">Search Research</h1>
            <p className="search-subheading">
              Find insights across Coda research documents and Intercom support
              conversations
            </p>

            <ResearchSearch
              value={query}
              onChange={setQuery}
              isSearching={isSearching}
              placeholder="Search for topics, themes, or keywords..."
              onClear={handleClearSearch}
            />

            <div className="filter-section">
              <SourceFilter
                selected={sourceFilter}
                onChange={setSourceFilter}
              />
            </div>
          </div>
        </section>

        {/* Results Section */}
        <section className="results-section">
          <div className="results-container">
            {useMockData && debouncedQuery && (
              <div className="mock-notice">
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="16" x2="12" y2="12" />
                  <line x1="12" y1="8" x2="12.01" y2="8" />
                </svg>
                <span>
                  Showing sample data. Backend search API is not yet available.
                </span>
              </div>
            )}

            <SearchResults
              results={results}
              isLoading={isSearching}
              query={debouncedQuery}
              onSimilar={handleSimilar}
            />
          </div>
        </section>

        {/* Keyboard Shortcuts */}
        <div className="keyboard-hints" aria-hidden="true">
          <span className="hint">
            <kbd>/</kbd> Focus search
          </span>
          <span className="hint">
            <kbd>Esc</kbd> Clear
          </span>
          <span className="hint">
            <kbd>Enter</kbd> Open result
          </span>
        </div>
      </main>

      <style jsx>{`
        .research-page {
          min-height: 100vh;
          background: var(--bg-void);
          display: flex;
          flex-direction: column;
        }

        /* Header */
        .page-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 12px 24px;
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 22%),
            hsl(0, 0%, 18%)
          );
          box-shadow: var(--shadow-md);
          position: sticky;
          top: 16px;
          margin: 16px 24px 0;
          border-radius: var(--radius-full);
          z-index: 10;
        }

        :global([data-theme="light"]) .page-header {
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 100%),
            hsl(0, 0%, 94%)
          );
        }

        .header-left {
          display: flex;
          align-items: center;
          gap: 14px;
        }

        .logo-link {
          background: none;
          border: none;
          cursor: pointer;
          padding: 0;
          display: flex;
          align-items: center;
          opacity: 0.9;
          transition: opacity 0.15s ease;
        }

        .logo-link:hover {
          opacity: 1;
        }

        .header-divider {
          width: 1px;
          height: 24px;
          background: var(--border-default);
        }

        .page-title {
          font-size: 16px;
          font-weight: 500;
          color: var(--text-secondary);
        }

        .header-right {
          display: flex;
          align-items: center;
          gap: 10px;
        }

        .header-right :global(.nav-link) {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 8px 14px;
          border-radius: var(--radius-full);
          font-size: 13px;
          font-weight: 500;
          color: var(--text-secondary);
          text-decoration: none;
          transition: all 0.15s ease;
        }

        .header-right :global(.nav-link):hover {
          color: var(--text-primary);
          background: var(--bg-hover);
        }

        /* Main Content */
        .page-content {
          flex: 1;
          padding: 40px 24px 80px;
        }

        /* Search Section */
        .search-section {
          max-width: 800px;
          margin: 0 auto 40px;
        }

        .search-container {
          display: flex;
          flex-direction: column;
          align-items: center;
          text-align: center;
        }

        .search-heading {
          font-size: 32px;
          font-weight: 700;
          color: var(--text-primary);
          margin: 0 0 8px 0;
        }

        .search-subheading {
          font-size: 16px;
          color: var(--text-secondary);
          margin: 0 0 32px 0;
          max-width: 500px;
        }

        .filter-section {
          margin-top: 20px;
        }

        /* Results Section */
        .results-section {
          max-width: 800px;
          margin: 0 auto;
        }

        .results-container {
          width: 100%;
        }

        .mock-notice {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 12px 16px;
          background: var(--accent-amber-dim);
          border: 1px solid var(--accent-amber);
          border-radius: var(--radius-md);
          margin-bottom: 20px;
          font-size: 13px;
          color: var(--accent-amber);
        }

        /* Keyboard Hints */
        .keyboard-hints {
          position: fixed;
          bottom: 24px;
          left: 50%;
          transform: translateX(-50%);
          display: flex;
          gap: 20px;
          padding: 10px 20px;
          background: var(--bg-surface);
          border: 1px solid var(--border-subtle);
          border-radius: var(--radius-full);
          box-shadow: var(--shadow-lg);
        }

        .hint {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 12px;
          color: var(--text-tertiary);
        }

        .hint kbd {
          padding: 2px 6px;
          background: var(--bg-elevated);
          border: 1px solid var(--border-default);
          border-radius: var(--radius-sm);
          font-family: var(--font-mono);
          font-size: 11px;
          color: var(--text-secondary);
        }

        @media (max-width: 640px) {
          .keyboard-hints {
            display: none;
          }

          .search-heading {
            font-size: 24px;
          }

          .page-content {
            padding: 24px 16px 60px;
          }
        }
      `}</style>
    </div>
  );
}
