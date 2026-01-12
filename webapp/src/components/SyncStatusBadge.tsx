"use client";

import { SyncState, SYNC_STATE_CONFIG } from "@/lib/types";

interface SyncStatusBadgeProps {
  state: SyncState;
  size?: "sm" | "md";
  showLabel?: boolean;
}

export function SyncStatusBadge({
  state,
  size = "sm",
  showLabel = false,
}: SyncStatusBadgeProps) {
  const config = SYNC_STATE_CONFIG[state];
  const dotSize = size === "sm" ? 6 : 8;
  const isPending = state === "pending";

  return (
    <div className="sync-badge" title={config.label}>
      <span
        className={`sync-dot ${isPending ? "pulse" : ""}`}
        style={{
          width: dotSize,
          height: dotSize,
          backgroundColor: config.color,
        }}
      />
      {showLabel && <span className="sync-label">{config.label}</span>}

      <style jsx>{`
        .sync-badge {
          display: inline-flex;
          align-items: center;
          gap: 6px;
        }

        .sync-dot {
          border-radius: 50%;
          flex-shrink: 0;
        }

        .sync-dot.pulse {
          animation: pulse 1.5s ease-in-out infinite;
        }

        @keyframes pulse {
          0%,
          100% {
            opacity: 1;
            transform: scale(1);
          }
          50% {
            opacity: 0.5;
            transform: scale(1.15);
          }
        }

        .sync-label {
          font-size: ${size === "sm" ? "11px" : "12px"};
          font-weight: 500;
          color: var(--text-secondary);
        }
      `}</style>
    </div>
  );
}
