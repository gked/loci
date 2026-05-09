import { useState, useRef, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Icon } from "./Icon.jsx";
import { TypeDot } from "./TypeDot.jsx";
import { searchNodes, getRecentNodes } from "../lib/api.js";
import { useDebounce } from "../hooks/useDebounce.js";

export function CommandBar({ open, onClose, onOpen }) {
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

  const results = debouncedQ.length >= 2 ? searchResults : recentNodes.slice(0, 6);

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, background: "rgba(20,18,12,0.18)",
        backdropFilter: "blur(2px)", zIndex: 100,
        display: "flex", justifyContent: "center", paddingTop: "14vh",
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          width: 540, background: "rgba(255,255,255,0.92)", backdropFilter: "blur(14px)",
          border: "1px solid var(--vault-rule)", borderRadius: 12,
          boxShadow: "var(--shadow-overlay)", overflow: "hidden", height: "fit-content",
        }}
      >
        <div style={{
          display: "flex", alignItems: "center", gap: 10, padding: "12px 16px",
          borderBottom: "1px solid var(--vault-rule)",
        }}>
          <Icon name="search" size={16} />
          <input
            ref={inputRef}
            value={q}
            onChange={e => setQ(e.target.value)}
            placeholder="Search vault — title, summary, alias…"
            style={{
              flex: 1, border: 0, outline: 0, background: "transparent",
              fontFamily: "var(--font-sans)", fontSize: 14, color: "var(--vault-fg)",
            }}
          />
          <span style={{
            fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--vault-fg-muted)",
            padding: "2px 6px", background: "var(--vault-sunken)", borderRadius: 3,
            border: "1px solid var(--vault-rule)",
          }}>esc</span>
        </div>
        <div style={{ maxHeight: 320, overflowY: "auto" }}>
          {results.length === 0 && debouncedQ.length >= 2 && (
            <div style={{ padding: "20px 16px", fontFamily: "var(--font-sans)", fontSize: 13, color: "var(--vault-fg-faint)", textAlign: "center", fontStyle: "italic" }}>
              No results for "{debouncedQ}"
            </div>
          )}
          {results.map((n, i) => (
            <button
              key={n.uid}
              onClick={() => { onOpen(n.uid); onClose(); }}
              style={{
                display: "flex", alignItems: "center", gap: 12, padding: "10px 16px",
                border: 0, background: i === 0 ? "var(--vault-sunken)" : "transparent",
                width: "100%", textAlign: "left", cursor: "pointer",
                borderBottom: "1px solid var(--vault-rule)", fontFamily: "var(--font-sans)",
              }}
            >
              <TypeDot type={n.type} />
              <span style={{ flex: 1, fontSize: 13, color: "var(--vault-fg)" }}>{n.title}</span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--vault-fg-faint)" }}>
                {n.type} · {n.uid}
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
