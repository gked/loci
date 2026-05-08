// Inner-shell components — vault explorer.
const TYPES = [
  ["project","#2f6fc4"],["task","#ff8a00"],["document","#1fa050"],
  ["entity","#e63946"],["conversation","#2dbfb6"],["article","#f4c430"],
  ["bookmark","#c062b8"],["procedure","#ff6b8a"],["topic","#a4421f"],
  ["event","#7a5cc1"],["asset","#5e7a8c"]
];
const TYPE_COLOR = Object.fromEntries(TYPES);

const TypeDot = ({ type, size = 10 }) => (
  <span style={{ display: "inline-block", width: size, height: size, borderRadius: "50%", background: TYPE_COLOR[type] || "#bab0ac", flexShrink: 0, boxShadow: "0 0 0 1px rgba(0,0,0,0.06)" }}/>
);

const TypeChip = ({ type }) => (
  <span style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "3px 10px", borderRadius: 999, fontSize: 12, fontWeight: 500, background: "var(--vault-sunken)", border: "1px solid var(--vault-rule)", color: "var(--vault-fg)" }}>
    <TypeDot type={type} size={8}/>{type}
  </span>
);

const RelationChip = ({ children }) => (
  <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, padding: "3px 8px", background: "#fff", border: "1px solid var(--vault-rule)", borderRadius: 3, color: "var(--vault-fg-muted)" }}>{children}</span>
);

const TagChip = ({ children }) => (
  <span style={{ fontSize: 11, color: "var(--vault-fg-muted)", fontFamily: "var(--font-mono)", padding: "2px 6px", background: "var(--vault-sunken)", borderRadius: 2 }}>#{children}</span>
);

const Icon = ({ name, size = 16 }) => {
  const paths = {
    search: <><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.35-4.35"/></>,
    plus: <><path d="M12 5v14M5 12h14"/></>,
    chevronRight: <><path d="M9 6l6 6-6 6"/></>,
    chevronDown: <><path d="M6 9l6 6 6-6"/></>,
    graph: <><circle cx="12" cy="12" r="3"/><circle cx="5" cy="6" r="2"/><circle cx="19" cy="6" r="2"/><circle cx="5" cy="18" r="2"/><circle cx="19" cy="18" r="2"/><path d="M7 7l3 3M17 7l-3 3M7 17l3-3M17 17l-3-3"/></>,
    inbox: <><polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11L2 12v6a2 2 0 002 2h16a2 2 0 002-2v-6l-3.45-6.89A2 2 0 0016.76 4H7.24a2 2 0 00-1.79 1.11z"/></>,
    settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 11-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 11-4 0v-.09a1.65 1.65 0 00-1-1.51 1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 11-2.83-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 110-4h.09a1.65 1.65 0 001.51-1 1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 112.83-2.83l.06.06a1.65 1.65 0 001.82.33h0a1.65 1.65 0 001-1.51V3a2 2 0 114 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 112.83 2.83l-.06.06a1.65 1.65 0 00-.33 1.82v0a1.65 1.65 0 001.51 1H21a2 2 0 110 4h-.09a1.65 1.65 0 00-1.51 1z"/></>,
    file: <><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><path d="M14 2v6h6"/></>,
    enter: <><polyline points="9 10 4 15 9 20"/><path d="M20 4v7a4 4 0 01-4 4H4"/></>
  };
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      {paths[name]}
    </svg>
  );
};

const Sidebar = ({ section, onNav, vault }) => {
  const counts = {};
  TYPES.forEach(([t]) => counts[t] = vault.filter(n => n.type === t).length);
  const tags = ["design-doc","protocol","journal","whitepaper","book"];
  const NavRow = ({ id, icon, label, count, type }) => (
    <button onClick={() => onNav(id)} style={{ display: "flex", alignItems: "center", gap: 10, padding: "6px 10px", border: 0, background: section === id ? "var(--vault-sunken)" : "transparent", borderRadius: 4, color: "var(--vault-fg)", fontFamily: "var(--font-sans)", fontSize: 13, fontWeight: section === id ? 600 : 400, cursor: "pointer", textAlign: "left", width: "100%" }}>
      {type ? <TypeDot type={type}/> : <Icon name={icon} size={14}/>}
      <span style={{ flex: 1 }}>{label}</span>
      {count != null && <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--vault-fg-faint)" }}>{count}</span>}
    </button>
  );
  return (
    <aside style={{ width: 260, flexShrink: 0, borderRight: "1px solid var(--vault-rule)", background: "var(--vault-bg)", height: "100vh", display: "flex", flexDirection: "column" }}>
      <div style={{ padding: "16px 16px 12px", display: "flex", alignItems: "center", gap: 10, borderBottom: "1px solid var(--vault-rule)" }}>
        <img src="../../assets/logo/monogram.svg" width="22" height="22" alt=""/>
        <span style={{ fontFamily: "var(--font-display)", fontSize: 22, fontWeight: 500, color: "var(--vault-fg)" }}>Loci</span>
        <span style={{ marginLeft: "auto", fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--vault-fg-faint)" }}>v0.4</span>
      </div>
      <div style={{ padding: "10px 8px", display: "flex", flexDirection: "column", gap: 1, overflowY: "auto" }}>
        <NavRow id="all" icon="inbox" label="All loci" count={vault.length}/>
        <NavRow id="recent" icon="enter" label="Recent" count={6}/>
        <NavRow id="graph" icon="graph" label="Graph"/>
        <div style={{ padding: "12px 10px 4px", fontSize: 10, fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--vault-fg-muted)" }}>Types</div>
        {TYPES.map(([t]) => <NavRow key={t} id={"t:"+t} type={t} label={t} count={counts[t]}/>)}
        <div style={{ padding: "12px 10px 4px", fontSize: 10, fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--vault-fg-muted)" }}>Tags</div>
        {tags.map(t => <NavRow key={t} id={"#"+t} icon="file" label={"#"+t}/>)}
      </div>
      <div style={{ marginTop: "auto", padding: 12, borderTop: "1px solid var(--vault-rule)", display: "flex", alignItems: "center", gap: 8, fontSize: 11, color: "var(--vault-fg-muted)" }}>
        <Icon name="settings" size={14}/><span>vault @ ~/Nextcloud/loci</span>
      </div>
    </aside>
  );
};

const NodeRow = ({ node, selected, onClick }) => (
  <button onClick={onClick} style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 14px", border: 0, background: selected ? "var(--vault-sunken)" : "transparent", borderBottom: "1px solid var(--vault-rule)", textAlign: "left", width: "100%", cursor: "pointer", fontFamily: "var(--font-sans)" }}>
    <TypeDot type={node.type}/>
    <span style={{ flex: 1, fontSize: 13, color: "var(--vault-fg)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{node.title}</span>
    <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--vault-fg-faint)" }}>{node.uid}</span>
  </button>
);

const FrontmatterGrid = ({ node }) => {
  const rows = [
    ["uid", node.uid, "mono"], ["type", node.type, "type"], ["created", node.created, "mono"],
    ["updated", node.updated, "mono"], ["status", node.status],
    ...(node.tags ? [["tags", node.tags.map(t => "#"+t).join(" ")]] : []),
    ...(node.domains ? [["domains", node.domains.join(", ")]] : []),
  ];
  return (
    <div style={{ background: "var(--vault-sunken)", borderRadius: 6, padding: "12px 14px", display: "grid", gridTemplateColumns: "100px 1fr", gap: "6px 14px", fontFamily: "var(--font-mono)", fontSize: 12 }}>
      {rows.map(([k, v, mode], i) => (
        <React.Fragment key={i}>
          <span style={{ color: "var(--vault-fg-muted)" }}>{k}</span>
          <span style={{ color: "var(--vault-fg)", display: "flex", alignItems: "center", gap: 6 }}>
            {mode === "type" && <TypeDot type={v}/>}{v}
          </span>
        </React.Fragment>
      ))}
    </div>
  );
};

const NodeDetail = ({ node, vault, onOpen }) => {
  const related = (node.relations || []).map(r => ({ ...r, target: vault.find(n => n.uid === r.uid) })).filter(r => r.target);
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 280px", gap: 32, padding: "24px 32px", overflowY: "auto", height: "100%", boxSizing: "border-box" }}>
      <div style={{ maxWidth: 720 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6, fontFamily: "var(--font-sans)", fontSize: 11, color: "var(--vault-fg-muted)", letterSpacing: "0.06em", textTransform: "uppercase" }}>
          <TypeDot type={node.type}/><span>{node.type}</span>
          <span>·</span><span style={{fontFamily:"var(--font-mono)",textTransform:"none",letterSpacing:0}}>{node.uid}</span>
        </div>
        <h1 style={{ fontFamily: "var(--font-serif)", fontWeight: 600, fontSize: 32, lineHeight: 1.2, letterSpacing: "-0.01em", margin: "0 0 16px", color: "var(--vault-fg)" }}>{node.title}</h1>
        <FrontmatterGrid node={node}/>
        <div style={{ marginTop: 20, fontFamily: "var(--font-serif)", fontSize: 16, lineHeight: 1.6, color: "var(--vault-fg)", textWrap: "pretty" }}>
          {node.body.split("\n\n").map((p, i) => <p key={i} style={{ margin: "0 0 14px" }}>{p}</p>)}
        </div>
      </div>
      <aside style={{ borderLeft: "1px solid var(--vault-rule)", paddingLeft: 24, fontFamily: "var(--font-sans)" }}>
        <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--vault-fg-muted)", marginBottom: 8 }}>Relations · {related.length}</div>
        {related.map((r, i) => (
          <button key={i} onClick={() => onOpen(r.target.uid)} style={{ display: "flex", alignItems: "flex-start", gap: 8, padding: "8px 0", border: 0, borderBottom: "1px dashed var(--vault-rule)", background: "transparent", width: "100%", textAlign: "left", cursor: "pointer" }}>
            <TypeDot type={r.target.type} size={8}/>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 12, color: "var(--vault-fg)", lineHeight: 1.3 }}>{r.target.title}</div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--vault-fg-muted)", marginTop: 2 }}>{r.type}</div>
            </div>
          </button>
        ))}
        {node.tags && (
          <>
            <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--vault-fg-muted)", margin: "20px 0 8px" }}>Tags</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
              {node.tags.map(t => <TagChip key={t}>{t}</TagChip>)}
            </div>
          </>
        )}
      </aside>
    </div>
  );
};

const CommandBar = ({ open, onClose, vault, onOpen }) => {
  const [q, setQ] = React.useState("");
  const inputRef = React.useRef();
  React.useEffect(() => { if (open) setTimeout(() => inputRef.current?.focus(), 50); }, [open]);
  const results = q ? vault.filter(n => n.title.toLowerCase().includes(q.toLowerCase()) || n.uid.includes(q)).slice(0, 6) : vault.slice(0, 6);
  if (!open) return null;
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(20,18,12,0.18)", backdropFilter: "blur(2px)", zIndex: 100, display: "flex", justifyContent: "center", paddingTop: "14vh" }}>
      <div onClick={e => e.stopPropagation()} style={{ width: 540, background: "rgba(255,255,255,0.92)", backdropFilter: "blur(14px)", border: "1px solid var(--vault-rule)", borderRadius: 12, boxShadow: "var(--shadow-overlay)", overflow: "hidden", height: "fit-content" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 16px", borderBottom: "1px solid var(--vault-rule)" }}>
          <Icon name="search" size={16}/>
          <input ref={inputRef} value={q} onChange={e => setQ(e.target.value)} placeholder="Search vault — title, tag, UID, or :type" style={{ flex: 1, border: 0, outline: 0, background: "transparent", fontFamily: "var(--font-sans)", fontSize: 14, color: "var(--vault-fg)" }}/>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--vault-fg-muted)", padding: "2px 6px", background: "var(--vault-sunken)", borderRadius: 3, border: "1px solid var(--vault-rule)" }}>esc</span>
        </div>
        <div style={{ maxHeight: 320, overflowY: "auto" }}>
          {results.map((n, i) => (
            <button key={n.uid} onClick={() => { onOpen(n.uid); onClose(); }} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 16px", border: 0, background: i === 0 ? "var(--vault-sunken)" : "transparent", width: "100%", textAlign: "left", cursor: "pointer", borderBottom: "1px solid var(--vault-rule)", fontFamily: "var(--font-sans)" }}>
              <TypeDot type={n.type}/>
              <span style={{ flex: 1, fontSize: 13, color: "var(--vault-fg)" }}>{n.title}</span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--vault-fg-faint)" }}>{n.type} · {n.uid}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};

const GraphView_OLD_RADIAL = ({ vault, onOpen }) => {
  // simple deterministic radial layout
  const W = 720, H = 520, cx = W/2, cy = H/2;
  const nodes = vault.map((n, i) => {
    const a = (i / vault.length) * Math.PI * 2;
    const r = 60 + (i % 3) * 80;
    return { ...n, x: cx + Math.cos(a) * r, y: cy + Math.sin(a) * r };
  });
  const byUid = Object.fromEntries(nodes.map(n => [n.uid, n]));
  const edges = nodes.flatMap(n => (n.relations||[]).map(r => byUid[r.uid] && [n, byUid[r.uid], r.type]).filter(Boolean));
  return (
    <div style={{ height: "100%", padding: 24, boxSizing: "border-box", display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
        <h1 style={{ fontFamily: "var(--font-serif)", fontWeight: 600, fontSize: 24, margin: 0 }}>Topology</h1>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--vault-fg-muted)" }}>{nodes.length} nodes · {edges.length} edges</span>
      </div>
      <div style={{ flex: 1, background: "#fff", border: "1px solid var(--vault-rule)", borderRadius: 6, overflow: "hidden" }}>
        <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "100%" }}>
          {edges.map(([a, b], i) => (
            <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#d8d5cd" strokeWidth="1"/>
          ))}
          {nodes.map(n => (
            <g key={n.uid} onClick={() => onOpen(n.uid)} style={{ cursor: "pointer" }}>
              <circle cx={n.x} cy={n.y} r="9" fill={TYPE_COLOR[n.type]} stroke="#fff" strokeWidth="1.5"/>
              <text x={n.x} y={n.y + 22} textAnchor="middle" fontFamily="Inter, sans-serif" fontSize="10" fill="var(--vault-fg-muted)">{n.title.length > 22 ? n.title.slice(0,22) + "…" : n.title}</text>
            </g>
          ))}
        </svg>
      </div>
    </div>
  );
};

Object.assign(window, { TypeDot, TypeChip, RelationChip, TagChip, Icon, Sidebar, NodeRow, FrontmatterGrid, NodeDetail, CommandBar, TYPES, TYPE_COLOR });
