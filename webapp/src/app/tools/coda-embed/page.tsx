"use client";

import { useState, useEffect, useRef } from "react";

const CODA_DOC_ID = "c4RRJ_VLtW";
const CODA_EMBED_BASE = `https://coda.io/embed/${CODA_DOC_ID}`;
const CODA_PAGE_ID = "_susSTOua"; // From embed code

export default function CodaEmbedPage() {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [messages, setMessages] = useState<string[]>([]);
  const [currentUrl, setCurrentUrl] = useState(
    `${CODA_EMBED_BASE}/${CODA_PAGE_ID}?viewMode=embedplay`,
  );
  const [discoveredPages, setDiscoveredPages] = useState<string[]>([]);

  // Listen for postMessage from Coda embed
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      // Log all messages from Coda
      const msg = `[${new Date().toISOString()}] ${event.origin}: ${JSON.stringify(event.data).substring(0, 200)}`;
      setMessages((prev) => [...prev.slice(-50), msg]);
      console.log("Coda message:", event);

      // Check if it contains page/navigation data
      if (event.data && typeof event.data === "object") {
        const dataStr = JSON.stringify(event.data);
        if (
          dataStr.includes("page") ||
          dataStr.includes("navigation") ||
          dataStr.includes("section")
        ) {
          console.log("📄 Potential page data:", event.data);
        }
      }
    };

    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, []);

  // Try to send message to iframe
  const sendMessage = (msg: object) => {
    if (iframeRef.current?.contentWindow) {
      iframeRef.current.contentWindow.postMessage(msg, "*");
      console.log("Sent:", msg);
    }
  };

  // Probe the embed for data
  const probeEmbed = () => {
    // Try common postMessage patterns
    sendMessage({ type: "getPages" });
    sendMessage({ type: "getNavigation" });
    sendMessage({ type: "getDocumentStructure" });
    sendMessage({ action: "getPages" });
    sendMessage({ command: "list" });
    sendMessage({ method: "getTableOfContents" });
  };

  return (
    <div className="min-h-screen bg-[var(--bg-void)] text-[var(--text-primary)] p-4">
      <h1 className="text-2xl font-bold mb-4">Coda Embed Explorer</h1>

      <div className="grid grid-cols-2 gap-4 h-[calc(100vh-120px)]">
        {/* Embed */}
        <div className="border border-[var(--border-default)] rounded-lg overflow-hidden">
          <div className="bg-[var(--bg-surface)] p-2 text-sm">
            <input
              type="text"
              value={currentUrl}
              onChange={(e) => setCurrentUrl(e.target.value)}
              className="w-full bg-[var(--bg-elevated)] text-[var(--text-primary)] px-2 py-1 rounded text-xs"
            />
          </div>
          <iframe
            ref={iframeRef}
            src={currentUrl}
            className="w-full h-[calc(100%-40px)]"
            allow="fullscreen"
          />
        </div>

        {/* Controls & Messages */}
        <div className="flex flex-col gap-4">
          {/* Controls */}
          <div className="bg-[var(--bg-surface)] p-4 rounded-lg">
            <h2 className="font-semibold mb-2">Controls</h2>
            <div className="flex gap-2 flex-wrap">
              <button
                onClick={probeEmbed}
                className="px-3 py-1 bg-[var(--accent-teal)] text-black rounded text-sm"
              >
                Probe Embed
              </button>
              <button
                onClick={() => setMessages([])}
                className="px-3 py-1 bg-[var(--bg-elevated)] rounded text-sm"
              >
                Clear Messages
              </button>
              <button
                onClick={() => {
                  // Try different viewModes
                  const modes = ["embedplay", "embed", "embedview"];
                  const current = new URL(currentUrl);
                  const currentMode =
                    current.searchParams.get("viewMode") || "embedplay";
                  const nextIndex =
                    (modes.indexOf(currentMode) + 1) % modes.length;
                  current.searchParams.set("viewMode", modes[nextIndex]);
                  setCurrentUrl(current.toString());
                }}
                className="px-3 py-1 bg-[var(--bg-elevated)] rounded text-sm"
              >
                Toggle ViewMode
              </button>
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 bg-[var(--bg-surface)] p-4 rounded-lg overflow-hidden">
            <h2 className="font-semibold mb-2">
              PostMessage Log ({messages.length})
            </h2>
            <div className="h-[calc(100%-30px)] overflow-auto font-mono text-xs">
              {messages.length === 0 ? (
                <p className="text-[var(--text-secondary)]">
                  No messages yet. Interact with the embed or click Probe.
                </p>
              ) : (
                messages.map((msg, i) => (
                  <div
                    key={i}
                    className="py-1 border-b border-[var(--border-subtle)]"
                  >
                    {msg}
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Discovered Pages */}
          <div className="bg-[var(--bg-surface)] p-4 rounded-lg max-h-48 overflow-auto">
            <h2 className="font-semibold mb-2">
              Discovered Pages ({discoveredPages.length})
            </h2>
            {discoveredPages.length === 0 ? (
              <p className="text-[var(--text-secondary)] text-sm">None yet</p>
            ) : (
              <ul className="text-sm">
                {discoveredPages.map((p, i) => (
                  <li key={i}>{p}</li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
