import { useState, useRef, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { TypeDot } from "./TypeDot.jsx";
import { searchNodes, getRecentNodes } from "../lib/api.js";
import { useDebounce } from "../hooks/useDebounce.js";

export function CommandPalette({ open, onClose, onOpen }) {
  const [q, setQ] = useState("");
  const inputRef = useRef();
  const debouncedQ = useDebounce(q, 150);

  useEffect(() => {
    if (open) {
      setQ("");
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  const { data: searchResults = [] } = useQuery({
    queryKey: ["search", debouncedQ],
    queryFn: () => searchNodes(debouncedQ),
    enabled: debouncedQ.length >= 2,
    staleTime: 30_000,
  });

  const { data: recentNodes = [] } = useQuery({
    queryKey: ["nodes/recent"],
    queryFn: getRecentNodes,
    staleTime: 60_000,
  });

  if (!open) return null;

  const results = debouncedQ.length >= 2 ? searchResults : recentNodes.slice(0, 7);

  return (
    <div
      onClick={onClose}
      style={{
        position: "absolute", inset: 0, zIndex: 50,
        background: "rgba(6,9,20,0.65)",
        backdropFilter: "blur(4px)",
        display: "flex", justifyContent: "center", paddingTop: "10vh",
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        data-testid="command-palette"
        style={{
          width: 560, maxHeight: "70vh",
          background: "rgba(10,16,32,0.92)",
          backdropFilter: "blur(20px)",
          border: "1px solid var(--t-bronze-d)",
          outline: "0.5px solid var(--t-bronze-d)",
          outlineOffset: 3,
          position: "relative", display: "flex", flexDirection: "column",
        }}
      >
        {/* corner reticles */}
        <span style={{ position: "absolute", top: -1, left: -1, width: 10, height: 10, borderTop: "1px solid var(--t-bronze)", borderLeft: "1px solid var(--t-bronze)" }}/>
        <span style={{ position: "absolute", top: -1, right: -1, width: 10, height: 10, borderTop: "1px solid var(--t-bronze)", borderRight: "1px solid var(--t-bronze)" }}/>
        <span style={{ position: "absolute", bottom: -1, left: -1, width: 10, height: 10, borderBottom: "1px solid var(--t-bronze)", borderLeft: "1px solid var(--t-bronze)" }}/>
        <span style={{ position: "absolute", bottom: -1, right: -1, width: 10, height: 10, borderBottom: "1px solid var(--t-bronze)", borderRight: "1px solid var(--t-bronze)" }}/>

        {/* header */}
        <div style={{
          padding: "10px 18px 0", display: "flex", alignItems: "baseline", gap: 10,
          fontFamily: "var(--font-display)", fontStyle: "italic", fontSize: 11,
          color: "var(--t-bronze)", letterSpacing: "0.18em", textTransform: "lowercase",
        }}>
          <span>praeceptum · command</span>
          <span style={{ flex: 1, height: 0, borderTop: "0.5px solid var(--t-bronze-d)" }}/>
          <span style={{ fontFamily: "var(--font-mono)", fontStyle: "normal", fontSize: 9, color: "var(--t-fg-faint)", letterSpacing: "0.04em" }}>
            esc to close
          </span>
        </div>

        {/* input */}
        <div style={{ padding: "4px 18px 14px", borderBottom: "1px solid var(--t-rule)" }}>
          <input
            ref={inputRef}
            value={q}
            onChange={e => setQ(e.target.value)}
            onKeyDown={e => { if (e.key === "Escape") onClose(); }}
            placeholder="search vault — title, tag, uid"
            aria-label="search vault"
            data-testid="palette-input"
            className="t-input"
            style={{ fontSize: 20 }}
          />
        </div>

        {/* results */}
        <div style={{ flex: 1, overflowY: "auto", padding: "6px 0" }}>
          {results.length === 0 && debouncedQ.length >= 2 && (
            <div data-testid="palette-empty" style={{ padding: "24px 18px", fontFamily: "var(--font-display)", fontStyle: "italic", fontSize: 13, color: "var(--t-fg-faint)", textAlign: "center" }}>
              vacuum · no results for "{debouncedQ}"
            </div>
          )}
          {results.map((n, i) => (
            <button
              key={n.uid}
              onClick={() => { onOpen(n.uid); onClose(); }}
              data-testid="palette-result"
              data-uid={n.uid}
              style={{
                display: "grid", gridTemplateColumns: "18px 1fr auto auto",
                alignItems: "center", gap: 14, padding: "8px 18px",
                border: 0,
                background: i === 0 ? "rgba(201,168,106,0.10)" : "transparent",
                color: "var(--t-fg)", textAlign: "left", width: "100%",
                cursor: "pointer", fontFamily: "var(--font-sans)", fontSize: 13,
                position: "relative",
              }}
            >
              {i === 0 && <span style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 2, background: "var(--t-bronze)" }}/>}
              <TypeDot type={n.type} size={8}/>
              <span style={{ fontFamily: "var(--font-serif)", fontSize: 14 }}>{n.title}</span>
              <span style={{ fontFamily: "var(--font-display)", fontStyle: "italic", fontSize: 10, color: "var(--t-bronze)", letterSpacing: "0.06em" }}>{n.type}</span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--t-fg-faint)", letterSpacing: "0.04em" }}>{n.uid}</span>
            </button>
          ))}
        </div>

        {/* footer */}
        <div style={{
          padding: "8px 18px", borderTop: "1px solid var(--t-rule)",
          display: "flex", gap: 18, fontFamily: "var(--font-mono)", fontSize: 9,
          color: "var(--t-fg-mute)", letterSpacing: "0.06em", textTransform: "uppercase",
        }}>
          <span>⏎ <span style={{ color: "var(--t-fg-faint)" }}>open</span></span>
          <span style={{ marginLeft: "auto", fontFamily: "var(--font-display)", fontStyle: "italic", fontSize: 10, letterSpacing: "0.18em", textTransform: "lowercase", color: "var(--t-bronze)" }}>
            {results.length} resultata
          </span>
        </div>
      </div>
    </div>
  );
}
