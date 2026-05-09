// NodeViewer — read-only node display.
// Phase 2 will swap in the Editor component for the body area.

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { TypeDot } from "./TypeDot.jsx";
import { FrontmatterPills } from "./FrontmatterPills.jsx";

export function NodeViewer({ node, onShowTopology }) {
  if (!node) {
    return (
      <div style={{
        flex: 1, display: "grid", placeItems: "center",
        color: "var(--vault-fg-faint)", fontFamily: "var(--font-serif)",
        fontStyle: "italic", fontSize: 18,
      }}>
        Select a locus from the right rail.
      </div>
    );
  }

  const wordCount = (node.body || "").trim().split(/\s+/).filter(Boolean).length;

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, background: "#fff", overflow: "hidden" }}>
      {/* toolbar */}
      <div style={{
        height: 44, padding: "0 24px", display: "flex", alignItems: "center", gap: 14,
        borderBottom: "1px solid var(--vault-rule)", flexShrink: 0,
      }}>
        <span style={{ display: "flex", alignItems: "center", gap: 8, fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--vault-fg-muted)" }}>
          <TypeDot type={node.type} />
          <span>{node.type}</span>
          <span style={{ color: "var(--vault-fg-faint)" }}>·</span>
          <span>{node.uid}</span>
        </span>
        <span style={{ flex: 1 }} />
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--vault-fg-faint)" }}>
          {wordCount}w
        </span>
        <button onClick={onShowTopology} style={{
          padding: "5px 9px", fontFamily: "var(--font-sans)", fontSize: 11,
          background: "transparent", color: "var(--vault-fg-muted)",
          border: "1px solid var(--vault-rule)", borderRadius: 4, cursor: "pointer",
          display: "inline-flex", alignItems: "center", gap: 5,
        }}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3"/>
            <circle cx="5" cy="6" r="2"/>
            <circle cx="19" cy="6" r="2"/>
            <circle cx="5" cy="18" r="2"/>
            <circle cx="19" cy="18" r="2"/>
            <path d="M7 7l3 3M17 7l-3 3M7 17l3-3M17 17l-3-3"/>
          </svg>
          show in topology
        </button>
      </div>

      {/* document */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        <div style={{ maxWidth: 760, margin: "0 auto", padding: "32px 48px 96px" }}>
          <h1 style={{
            fontFamily: "var(--font-serif)", fontWeight: 600, fontSize: 36,
            lineHeight: 1.15, letterSpacing: "-0.01em", color: "var(--vault-fg)",
            margin: "0 0 14px",
          }}>
            {node.title}
          </h1>

          <FrontmatterPills node={node} />

          <div className="inner-shell" style={{ marginTop: 24, fontFamily: "var(--font-serif)", fontSize: 17, lineHeight: 1.65, color: "var(--vault-fg)" }}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {node.body || ""}
            </ReactMarkdown>
          </div>

          {node.asset && (
            <div style={{
              marginTop: 32, padding: "14px 16px",
              background: "var(--vault-sunken)", borderRadius: 6,
              fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--vault-fg-muted)",
            }}>
              <div style={{ marginBottom: 6, fontWeight: 600, color: "var(--vault-fg)" }}>Asset</div>
              <div>{node.asset.mime_type} · {(node.asset.size_bytes / 1024).toFixed(1)} KB</div>
              <div style={{ marginTop: 4, wordBreak: "break-all" }}>{node.asset.path}</div>
              {node.asset.content && (
                <pre style={{
                  marginTop: 12, padding: "10px 12px", background: "#fff",
                  border: "1px solid var(--vault-rule)", borderRadius: 4,
                  fontSize: 11, overflowX: "auto", whiteSpace: "pre-wrap",
                }}>
                  {node.asset.content.slice(0, 4000)}
                  {node.asset.content.length > 4000 ? "\n… truncated" : ""}
                </pre>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
