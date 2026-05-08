// Editor.jsx — primary editing surface (left, full-bleed)
//
// Markdown editor over the node body. Frontmatter renders as an editable
// pill grid on top. Title is a contenteditable h1 in the display serif.
// All edits are local-state — this is a hi-fi mock, not a real save layer.

const Editor = ({ node, onChange, onCmd }) => {
  if (!node) return (
    <div style={{ flex: 1, display: "grid", placeItems: "center", color: "var(--vault-fg-faint)", fontFamily: "var(--font-serif)", fontStyle: "italic", fontSize: 18 }}>
      Select a locus from the right rail.
    </div>
  );

  const [draft, setDraft] = React.useState(node.body);
  const [title, setTitle] = React.useState(node.title);
  const [dirty, setDirty] = React.useState(false);

  React.useEffect(() => { setDraft(node.body); setTitle(node.title); setDirty(false); }, [node.uid]);

  const onBody = (e) => { setDraft(e.target.value); setDirty(true); };
  const onTitle = (e) => { setTitle(e.target.value); setDirty(true); };

  const wordCount = draft.trim().split(/\s+/).filter(Boolean).length;
  const charCount = draft.length;

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, background: "#fff", overflow: "hidden" }}>
      {/* editor toolbar */}
      <div style={{ height: 44, padding: "0 24px", display: "flex", alignItems: "center", gap: 14, borderBottom: "1px solid var(--vault-rule)", flexShrink: 0 }}>
        <span style={{ display: "flex", alignItems: "center", gap: 8, fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--vault-fg-muted)" }}>
          <TypeDot type={node.type}/><span>{node.type}</span>
          <span style={{ color: "var(--vault-fg-faint)" }}>·</span><span>{node.uid}</span>
        </span>
        <span style={{ flex: 1 }}/>
        <span style={{ display: "flex", alignItems: "center", gap: 4, fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--vault-fg-faint)" }}>
          <span>{wordCount}w</span><span>·</span><span>{charCount}c</span>
        </span>
        {dirty && <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--vault-warn)" }}>● unsaved</span>}
        <button onClick={() => onCmd && onCmd("graph")} title="show this node in topology — G" style={{
          padding: "5px 9px", fontFamily: "var(--font-sans)", fontSize: 11,
          background: "transparent", color: "var(--vault-fg-muted)",
          border: "1px solid var(--vault-rule)", borderRadius: 4, cursor: "pointer",
          display: "inline-flex", alignItems: "center", gap: 5
        }}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3"/><circle cx="5" cy="6" r="2"/><circle cx="19" cy="6" r="2"/><circle cx="5" cy="18" r="2"/><circle cx="19" cy="18" r="2"/><path d="M7 7l3 3M17 7l-3 3M7 17l3-3M17 17l-3-3"/>
          </svg>
          show in topology
        </button>
        <button onClick={() => { onChange && onChange({ ...node, title, body: draft }); setDirty(false); }} style={{
          padding: "5px 12px", fontFamily: "var(--font-sans)", fontSize: 12,
          background: dirty ? "var(--vault-fg)" : "var(--vault-sunken)",
          color: dirty ? "#fff" : "var(--vault-fg-muted)",
          border: "1px solid " + (dirty ? "var(--vault-fg)" : "var(--vault-rule)"),
          borderRadius: 4, cursor: dirty ? "pointer" : "default"
        }}>save · ⌘S</button>
        <button onClick={() => onCmd && onCmd("close")} title="close" style={{ width: 26, height: 26, display: "grid", placeItems: "center", border: 0, background: "transparent", cursor: "pointer", color: "var(--vault-fg-muted)" }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M18 6 6 18M6 6l12 12"/></svg>
        </button>
      </div>

      {/* document */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        <div style={{ maxWidth: 760, margin: "0 auto", padding: "32px 48px 96px" }}>
          {/* title */}
          <input value={title} onChange={onTitle} style={{
            width: "100%", border: 0, outline: 0, padding: 0, margin: "0 0 14px",
            fontFamily: "var(--font-serif)", fontWeight: 600, fontSize: 36,
            lineHeight: 1.15, letterSpacing: "-0.01em", color: "var(--vault-fg)",
            background: "transparent"
          }}/>

          {/* frontmatter pills */}
          <FrontmatterPills node={node}/>

          {/* body — monospace markdown editor */}
          <textarea value={draft} onChange={onBody} spellCheck={false} style={{
            display: "block", width: "100%", minHeight: 420, marginTop: 24,
            border: 0, outline: 0, resize: "none", padding: 0,
            fontFamily: "var(--font-serif)", fontSize: 17, lineHeight: 1.65,
            color: "var(--vault-fg)", background: "transparent",
            caretColor: "var(--vault-focus)"
          }}/>
        </div>
      </div>
    </div>
  );
};

const FrontmatterPills = ({ node }) => {
  const Pill = ({ k, children, mono }) => (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 6,
      padding: "3px 8px 3px 4px", borderRadius: 3,
      background: "var(--vault-sunken)", border: "1px solid var(--vault-rule)",
      fontFamily: mono ? "var(--font-mono)" : "var(--font-sans)", fontSize: 11
    }}>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--vault-fg-muted)", letterSpacing: "0.05em", textTransform: "uppercase", padding: "1px 4px", background: "#fff", borderRadius: 2 }}>{k}</span>
      <span style={{ color: "var(--vault-fg)" }}>{children}</span>
    </span>
  );
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 4 }}>
      <Pill k="created" mono>{node.created}</Pill>
      <Pill k="updated" mono>{node.updated}</Pill>
      {node.status && <Pill k="status">{node.status}</Pill>}
      {(node.tags || []).map(t => (
        <span key={t} style={{ padding: "3px 8px", borderRadius: 3, background: "#fff", border: "1px solid var(--vault-rule)", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--vault-fg-muted)" }}>#{t}</span>
      ))}
      {(node.domains || []).map(d => (
        <span key={d} style={{ padding: "3px 8px", borderRadius: 3, background: "#fff", border: "1px solid var(--vault-rule)", fontFamily: "var(--font-sans)", fontSize: 11, color: "var(--vault-fg-muted)", fontStyle: "italic" }}>{d}</span>
      ))}
    </div>
  );
};

window.Editor = Editor;
