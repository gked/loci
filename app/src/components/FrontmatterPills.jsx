// FrontmatterPills — created/updated/status/tags/domains pills for NodeViewer toolbar

function Pill({ k, children, mono }) {
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 6,
      padding: "3px 8px 3px 4px", borderRadius: 3,
      background: "var(--vault-sunken)", border: "1px solid var(--vault-rule)",
      fontFamily: mono ? "var(--font-mono)" : "var(--font-sans)", fontSize: 11,
    }}>
      <span style={{
        fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--vault-fg-muted)",
        letterSpacing: "0.05em", textTransform: "uppercase",
        padding: "1px 4px", background: "#fff", borderRadius: 2,
      }}>{k}</span>
      <span style={{ color: "var(--vault-fg)" }}>{children}</span>
    </span>
  );
}

export function FrontmatterPills({ node }) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 4 }}>
      {node.created_at && <Pill k="created" mono>{node.created_at}</Pill>}
      {node.updated_at && <Pill k="updated" mono>{node.updated_at}</Pill>}
      {node.status && <Pill k="status">{node.status}</Pill>}
      {(node.tags || []).map(t => (
        <span key={t} style={{
          padding: "3px 8px", borderRadius: 3,
          background: "#fff", border: "1px solid var(--vault-rule)",
          fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--vault-fg-muted)",
        }}>#{t}</span>
      ))}
      {(node.domains || []).map(d => (
        <span key={d} style={{
          padding: "3px 8px", borderRadius: 3,
          background: "#fff", border: "1px solid var(--vault-rule)",
          fontFamily: "var(--font-sans)", fontSize: 11, color: "var(--vault-fg-muted)",
          fontStyle: "italic",
        }}>{d}</span>
      ))}
    </div>
  );
}
