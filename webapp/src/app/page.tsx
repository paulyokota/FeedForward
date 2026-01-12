"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import type { Story, StatusKey, BoardView } from "@/lib/types";
import { STATUS_ORDER, STATUS_CONFIG, PRIORITY_CONFIG } from "@/lib/types";
import { DroppableColumn } from "@/components/DroppableColumn";
import { DndBoardProvider } from "@/components/DndBoardProvider";
import { ThemeToggle } from "@/components/ThemeToggle";
import { CreateStoryModal } from "@/components/CreateStoryModal";
import { FeedForwardLogo } from "@/components/FeedForwardLogo";
import type { StoryMoveEvent } from "@/lib/dnd.types";
import Link from "next/link";

type PriorityFilter = "all" | "urgent" | "high" | "medium" | "low" | "none";

export default function BoardPage() {
  const [board, setBoard] = useState<BoardView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<Story[] | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [priorityFilter, setPriorityFilter] = useState<PriorityFilter>("all");
  const [productAreaFilter, setProductAreaFilter] = useState<string>("");

  const fetchBoard = useCallback(async () => {
    try {
      const data = await api.stories.board();
      setBoard(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load board");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchBoard();
  }, [fetchBoard]);

  // Debounced search
  useEffect(() => {
    if (!searchQuery.trim()) {
      setSearchResults(null);
      return;
    }

    const timer = setTimeout(async () => {
      setIsSearching(true);
      try {
        const results = await api.stories.search(searchQuery);
        setSearchResults(results);
      } catch (err) {
        console.error("Search error:", err);
      } finally {
        setIsSearching(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [searchQuery]);

  const handleStoryCreated = (story: Story) => {
    // Add story to the appropriate column
    setBoard((prev) => {
      if (!prev) return prev;
      const status = story.status as StatusKey;
      return {
        ...prev,
        [status]: [story, ...(prev[status] || [])],
      };
    });
  };

  const handleStoryMove = useCallback(
    async (event: StoryMoveEvent) => {
      if (!board) return;

      const { storyId, sourceStatus, targetStatus, sourceIndex, targetIndex } =
        event;

      // Find the story being moved
      const sourceStories = board[sourceStatus] as Story[];
      const story = sourceStories.find((s) => s.id === storyId);
      if (!story) return;

      // Optimistic update
      setBoard((prev) => {
        if (!prev) return prev;

        const updatedStory = { ...story, status: targetStatus };

        if (sourceStatus === targetStatus) {
          // Moving within same column - reorder only
          const columnStories = (prev[sourceStatus] as Story[]).filter(
            (s) => s.id !== storyId,
          );

          // Adjust target index: when source is above target, removing source
          // shifts subsequent cards up, so we need to compensate
          const adjustedIndex =
            sourceIndex < targetIndex ? targetIndex - 1 : targetIndex;

          columnStories.splice(adjustedIndex, 0, updatedStory);
          return {
            ...prev,
            [sourceStatus]: columnStories,
          };
        } else {
          // Moving to different column
          const newSource = (prev[sourceStatus] as Story[]).filter(
            (s) => s.id !== storyId,
          );
          const newTarget = [...((prev[targetStatus] as Story[]) || [])];
          newTarget.splice(targetIndex, 0, updatedStory);
          return {
            ...prev,
            [sourceStatus]: newSource,
            [targetStatus]: newTarget,
          };
        }
      });

      // Persist to API
      try {
        await api.stories.update(storyId, { status: targetStatus });
      } catch (err) {
        console.error("Failed to update story status:", err);
        // Revert on error
        fetchBoard();
      }
    },
    [board, fetchBoard],
  );

  // Filter stories in each column
  const filterStories = (stories: Story[]): Story[] => {
    return stories.filter((story) => {
      // Priority filter
      if (priorityFilter !== "all") {
        if (priorityFilter === "none" && story.priority !== null) return false;
        if (priorityFilter !== "none" && story.priority !== priorityFilter)
          return false;
      }

      // Product area filter
      if (productAreaFilter) {
        if (
          !story.product_area
            ?.toLowerCase()
            .includes(productAreaFilter.toLowerCase())
        ) {
          return false;
        }
      }

      return true;
    });
  };

  // Get unique product areas from all stories
  const productAreas: string[] = board
    ? [
        ...new Set(
          Object.values(board)
            .flat()
            .map((s) => s.product_area)
            .filter(
              (area): area is string => area !== null && area !== undefined,
            ),
        ),
      ]
    : [];

  const hasActiveFilters = priorityFilter !== "all" || productAreaFilter !== "";

  const clearFilters = () => {
    setPriorityFilter("all");
    setProductAreaFilter("");
  };

  // Get total story count (filtered)
  const getFilteredTotal = () => {
    if (!board) return 0;
    return Object.values(board)
      .map((stories) => filterStories(stories as Story[]))
      .flat().length;
  };

  if (loading) {
    return (
      <div className="loading-container loading-delayed">
        <div className="loading-spinner" />
        <span>Loading stories...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="error-container">
        <p>Error: {error}</p>
        <button onClick={() => window.location.reload()}>Retry</button>
      </div>
    );
  }

  return (
    <div className="board-layout">
      <header className="board-header">
        <div className="header-left">
          <FeedForwardLogo size="sm" />
          <div className="header-divider" />
          <span className="page-subtitle">Stories</span>
          <span className="story-total">{getFilteredTotal()} total</span>
        </div>

        <div className="header-center">
          <div className="search-wrapper">
            <svg
              className="search-icon"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input
              type="text"
              className="search-input"
              placeholder="Search stories..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            {isSearching && <div className="search-spinner" />}
            {searchQuery && !isSearching && (
              <button
                className="search-clear"
                onClick={() => setSearchQuery("")}
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
              </button>
            )}
          </div>

          {/* Search Results Dropdown */}
          {searchResults && searchResults.length > 0 && (
            <div className="search-results">
              {searchResults.slice(0, 8).map((story) => (
                <a
                  key={story.id}
                  href={`/story/${story.id}`}
                  className="search-result-item"
                >
                  <span
                    className="result-status"
                    style={{
                      backgroundColor:
                        STATUS_CONFIG[story.status as StatusKey]?.color,
                    }}
                  />
                  <span className="result-title">{story.title}</span>
                  {story.product_area && (
                    <span className="result-area">{story.product_area}</span>
                  )}
                </a>
              ))}
              {searchResults.length > 8 && (
                <div className="search-more">
                  +{searchResults.length - 8} more results
                </div>
              )}
            </div>
          )}
          {searchResults && searchResults.length === 0 && (
            <div className="search-results">
              <div className="search-empty">No stories found</div>
            </div>
          )}
        </div>

        <div className="header-actions">
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
          <div className="filter-wrapper">
            <button
              className={`btn-secondary ${hasActiveFilters ? "active" : ""}`}
              onClick={() => setIsFilterOpen(!isFilterOpen)}
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
              </svg>
              Filter
              {hasActiveFilters && <span className="filter-badge" />}
            </button>

            {isFilterOpen && (
              <div className="filter-dropdown">
                <div className="filter-header">
                  <span>Filters</span>
                  {hasActiveFilters && (
                    <button className="clear-filters" onClick={clearFilters}>
                      Clear
                    </button>
                  )}
                </div>

                <div className="filter-section">
                  <label>Priority</label>
                  <select
                    value={priorityFilter}
                    onChange={(e) =>
                      setPriorityFilter(e.target.value as PriorityFilter)
                    }
                  >
                    <option value="all">All priorities</option>
                    <option value="urgent">Urgent</option>
                    <option value="high">High</option>
                    <option value="medium">Medium</option>
                    <option value="low">Low</option>
                    <option value="none">No priority</option>
                  </select>
                </div>

                <div className="filter-section">
                  <label>Product Area</label>
                  <select
                    value={productAreaFilter}
                    onChange={(e) => setProductAreaFilter(e.target.value)}
                  >
                    <option value="">All areas</option>
                    {productAreas.map((area) => (
                      <option key={area} value={area}>
                        {area}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            )}
          </div>

          <button
            className="btn-primary"
            onClick={() => setIsCreateModalOpen(true)}
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            New Story
          </button>
        </div>
      </header>

      <DndBoardProvider onStoryMove={handleStoryMove}>
        <div className="board-container">
          {STATUS_ORDER.map((status) => (
            <DroppableColumn
              key={status}
              status={status}
              stories={filterStories((board?.[status] as Story[]) || [])}
            />
          ))}
        </div>
      </DndBoardProvider>

      <CreateStoryModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        onCreated={handleStoryCreated}
      />

      {/* Click outside to close filter */}
      {isFilterOpen && (
        <div
          className="filter-backdrop"
          onClick={() => setIsFilterOpen(false)}
        />
      )}

      <style jsx>{`
        .board-layout {
          min-height: 100vh;
          display: flex;
          flex-direction: column;
        }

        .board-header {
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
          gap: 20px;
        }

        :global([data-theme="light"]) .board-header {
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
          flex-shrink: 0;
        }

        .header-divider {
          width: 1px;
          height: 24px;
          background: var(--border-default);
        }

        .page-subtitle {
          font-size: 16px;
          font-weight: 500;
          color: var(--text-secondary);
        }

        .story-total {
          font-size: 13px;
          font-weight: 500;
          color: var(--text-secondary);
          background: var(--bg-elevated);
          padding: 4px 10px;
          border-radius: 12px;
        }

        .header-center {
          flex: 1;
          max-width: 400px;
          position: relative;
        }

        .search-wrapper {
          position: relative;
          display: flex;
          align-items: center;
        }

        .search-icon {
          position: absolute;
          left: 16px;
          color: white;
          pointer-events: none;
        }

        :global([data-theme="light"]) .search-icon {
          color: var(--text-muted);
        }

        .search-input {
          width: 100%;
          padding: 10px 40px;
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 32%),
            hsl(0, 0%, 28%)
          );
          border: none;
          border-radius: var(--radius-full);
          color: var(--text-primary);
          font-size: 13px;
          box-shadow: var(--shadow-sm);
        }

        :global([data-theme="light"]) .search-input {
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 96%),
            hsl(0, 0%, 90%)
          );
          box-shadow: var(--shadow-inset);
        }

        .search-input:focus {
          outline: 2px solid var(--accent-blue);
          outline-offset: -2px;
        }

        .search-input::placeholder {
          color: white;
        }

        :global([data-theme="light"]) .search-input::placeholder {
          color: var(--text-muted);
        }

        .search-spinner {
          position: absolute;
          right: 12px;
          width: 14px;
          height: 14px;
          border: 2px solid var(--border-default);
          border-top-color: var(--accent-blue);
          border-radius: 50%;
          animation: spin 0.6s linear infinite;
        }

        .search-clear {
          position: absolute;
          right: 8px;
          background: none;
          border: none;
          color: var(--text-muted);
          cursor: pointer;
          padding: 4px;
          border-radius: 4px;
        }

        .search-clear:hover {
          color: var(--text-primary);
          background: var(--bg-hover);
        }

        .search-results {
          position: absolute;
          top: calc(100% + 8px);
          left: 0;
          right: 0;
          background: var(--bg-surface);
          border: none;
          border-radius: var(--radius-md);
          box-shadow: var(--shadow-lg);
          z-index: 20;
          max-height: 400px;
          overflow-y: auto;
        }

        .search-result-item {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 10px 14px;
          text-decoration: none;
          color: var(--text-primary);
          border-bottom: 1px solid var(--border-subtle);
          transition: background 0.1s ease;
        }

        .search-result-item:hover {
          background: var(--bg-hover);
        }

        .search-result-item:last-child {
          border-bottom: none;
        }

        .result-status {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          flex-shrink: 0;
        }

        .result-title {
          flex: 1;
          font-size: 13px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .result-area {
          font-size: 11px;
          color: var(--text-tertiary);
          background: var(--bg-elevated);
          padding: 2px 8px;
          border-radius: 4px;
          flex-shrink: 0;
        }

        .search-more,
        .search-empty {
          padding: 10px 14px;
          font-size: 12px;
          color: var(--text-tertiary);
          text-align: center;
        }

        .header-actions {
          display: flex;
          align-items: center;
          gap: 10px;
          flex-shrink: 0;
        }

        .header-actions :global(.nav-link) {
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

        .header-actions :global(.nav-link):hover {
          color: var(--text-primary);
          background: var(--bg-hover);
        }

        .filter-wrapper {
          position: relative;
        }

        .btn-secondary,
        .btn-primary {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 8px 18px;
          border-radius: var(--radius-full);
          font-size: 13px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s ease;
        }

        .btn-secondary {
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 32%),
            hsl(0, 0%, 28%)
          );
          border: none;
          color: var(--text-secondary);
          box-shadow: var(--shadow-sm);
        }

        :global([data-theme="light"]) .btn-secondary {
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 96%),
            hsl(0, 0%, 90%)
          );
        }

        .btn-secondary:hover,
        .btn-secondary.active {
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 38%),
            hsl(0, 0%, 32%)
          );
          color: var(--text-primary);
          box-shadow: var(--shadow-md);
        }

        :global([data-theme="light"]) .btn-secondary:hover,
        :global([data-theme="light"]) .btn-secondary.active {
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 100%),
            hsl(0, 0%, 94%)
          );
        }

        .filter-badge {
          width: 6px;
          height: 6px;
          background: var(--accent-blue);
          border-radius: 50%;
        }

        .filter-dropdown {
          position: absolute;
          top: calc(100% + 8px);
          right: 0;
          width: 240px;
          background: var(--bg-surface);
          border: none;
          border-radius: var(--radius-md);
          box-shadow: var(--shadow-lg);
          z-index: 30;
          padding: 16px;
        }

        .filter-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 16px;
          font-size: 13px;
          font-weight: 600;
          color: var(--text-primary);
        }

        .clear-filters {
          background: none;
          border: none;
          color: var(--accent-blue);
          font-size: 12px;
          cursor: pointer;
        }

        .clear-filters:hover {
          text-decoration: underline;
        }

        .filter-section {
          margin-bottom: 14px;
        }

        .filter-section:last-child {
          margin-bottom: 0;
        }

        .filter-section label {
          display: block;
          font-size: 12px;
          color: var(--text-tertiary);
          margin-bottom: 6px;
        }

        .filter-section select {
          width: 100%;
          padding: 8px 10px;
          background: var(--bg-elevated);
          border: none;
          border-radius: var(--radius-md);
          color: var(--text-primary);
          font-size: 13px;
          cursor: pointer;
          box-shadow: var(--shadow-inset);
        }

        .filter-section select:focus {
          outline: 2px solid var(--accent-blue);
          outline-offset: -2px;
        }

        .filter-backdrop {
          position: fixed;
          inset: 0;
          z-index: 25;
        }

        .btn-primary {
          background: var(--accent-blue);
          border: none;
          color: white;
          font-weight: 600;
          box-shadow: var(--shadow-sm);
        }

        .btn-primary:hover {
          background: #74b3ff;
          box-shadow: var(--shadow-md);
        }

        .board-container {
          flex: 1;
          display: flex;
          gap: 16px;
          padding: 24px 28px;
          overflow-x: auto;
          background: var(--bg-void);
        }

        .loading-container {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          min-height: 100vh;
          gap: 16px;
          color: var(--text-secondary);
          font-size: 14px;
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

        .error-container {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          min-height: 100vh;
          gap: 20px;
          color: var(--text-secondary);
        }

        .error-container p {
          font-size: 15px;
          color: var(--accent-red);
        }

        .error-container button {
          padding: 10px 20px;
          background: var(--bg-surface);
          border: none;
          border-radius: var(--radius-md);
          color: var(--text-primary);
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s ease;
          box-shadow: var(--shadow-sm);
        }

        .error-container button:hover {
          background: var(--bg-elevated);
          box-shadow: var(--shadow-md);
        }
      `}</style>
    </div>
  );
}
