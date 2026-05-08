// RightRail — combined explorer
//
// Three tabs in one panel on the right side of the screen:
//   1. Vault   — sources of nodes: All / Recent / by type / by tag / Graph
//   2. Loci    — flat list of nodes filtered by the active source
//   3. Links   — incoming + outgoing relations for the active node
//
// One panel, one keyboard target, no left sidebar competing for attention.

const RightRail = ({ section, onNav, vault, selectedUid, onOpenUid, onOpenGraph }) => {
  const [tab, setTab] = React.useState("loci");
  const selected = vault.find(n => n.uid === selectedUid);

  const filtered = section === "all" ? vault
    : section === "recent" ? [...vault].sort((a,b) => b.updated.localeCompare(a.updated)).slice(0, 8)
    : section.startsWith("t:") ? vault.filter(n => n.type === section.slice(2))
    : section.startsWith("#") ? vault.filter(n => (n.tags || []).includes(section.slice(1)))
    : vault;

  const sectionLabel = section === "all" ? "All loci"
    : section === "recent" ? "Recently updated"
    : section.startsWith("t:") ? section.slice(2)
    : section.startsWith("#") ? section
    : section;

  return (
    <aside style={{ width: 360, flexShrink: 0, borderLeft: "1px solid var(--vault-rule)", background: "var(--vault-bg)", display: "flex", flexDirection: "column", minHeight: 0 }}>
      {/* tabs */}
      <div style={{ display: "flex", borderBottom: "1px solid var(--vault-rule)", background: "#fff", flexShrink: 0 }}>
        {[["vault","Vault"],["loci","Loci"],["links","Links"]].map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)} style={{
            flex: 1, padding: "12px 0", border: 0, background: "transparent",
            fontFamily: "var(--font-sans)", fontSize: 12, fontWeight: tab === id ? 600 : 400,
            color: tab === id ? "var(--vault-fg)" : "var(--vault-fg-muted)",
            borderBottom: "2px solid " + (tab === id ? "var(--vault-fg)" : "transparent"),
            cursor: "pointer", letterSpacing: "0.02em",
            display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6
          }}>
            {label}
            {id === "links" && selected && <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--vault-fg-muted)", padding: "1px 5px", background: "var(--vault-sunken)", borderRadius: 8 }}>{(selected.relations || []).length}</span>}
            {id === "loci" && <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--vault-fg-muted)", padding: "1px 5px", background: "var(--vault-sunken)", borderRadius: 8 }}>{filtered.length}</span>}
          </button>
        ))}
      </div>

      {/* tab content */}
      <div style={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
        {tab === "vault" && <VaultPanel section={section} onNav={onNav} vault={vault} onOpenGraph={onOpenGraph}/>}
        {tab === "loci" && <LociPanel sectionLabel={sectionLabel} nodes={filtered} selectedUid={selectedUid} onOpenUid={onOpenUid}/>}
        {tab === "links" && <LinksPanel node={selected} vault={vault} onOpenUid={onOpenUid}/>}
      </div>

      {/* footer — open vault location */}
      <div style={{ padding: "10px 14px", borderTop: "1px solid var(--vault-rule)", display: "flex", alignItems: "center", gap: 8, fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--vault-fg-muted)", flexShrink: 0 }}>
        <Icon name="settings" size={11}/><span>~/Nextcloud/loci</span>
      </div>
    </aside>
  );
};

const VaultPanel = ({ section, onNav, vault, onOpenGraph }) => {
  const counts = {};
  TYPES.forEach(([t]) => counts[t] = vault.filter(n => n.type === t).length);
  const tags = ["design-doc","protocol","journal","whitepaper","memory"];

  const Row = ({ id, icon, label, count, type, onClick }) => (
    <button onClick={onClick || (() => onNav(id))} style={{
      display: "flex", alignItems: "center", gap: 10, padding: "7px 14px",
      border: 0, background: section === id ? "var(--vault-sunken)" : "transparent",
      color: "var(--vault-fg)", fontFamily: "var(--font-sans)", fontSize: 13,
      fontWeight: section === id ? 600 : 400, cursor: "pointer", textAlign: "left", width: "100%"
    }}>
      {type ? <TypeDot type={type}/> : <Icon name={icon} size={14}/>}
      <span style={{ flex: 1 }}>{label}</span>
      {count != null && <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--vault-fg-faint)" }}>{count}</span>}
    </button>
  );

  const Heading = ({ children }) => (
    <div style={{ padding: "14px 14px 4px", fontSize: 10, fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--vault-fg-muted)" }}>{children}</div>
  );

  return (
    <div style={{ padding: "8px 0" }}>
      <Row id="all" icon="inbox" label="All loci" count={vault.length}/>
      <Row id="recent" icon="enter" label="Recent" count={8}/>
      <Row id="graph" icon="graph" label="Topology" onClick={onOpenGraph}/>
      <Heading>Types</Heading>
      {TYPES.filter(([t]) => counts[t] > 0).map(([t]) => <Row key={t} id={"t:"+t} type={t} label={t} count={counts[t]}/>)}
      <Heading>Tags</Heading>
      {tags.map(t => <Row key={t} id={"#"+t} icon="file" label={"#"+t}/>)}
    </div>
  );
};

const LociPanel = ({ sectionLabel, nodes, selectedUid, onOpenUid }) => (
  <div>
    <div style={{ padding: "12px 16px 8px", display: "flex", alignItems: "baseline", gap: 8, position: "sticky", top: 0, background: "var(--vault-bg)", zIndex: 1, borderBottom: "1px solid var(--vault-rule)" }}>
      <span style={{ fontFamily: "var(--font-sans)", fontSize: 10, fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--vault-fg-muted)" }}>{sectionLabel}</span>
    </div>
    {nodes.map(n => (
      <button key={n.uid} onClick={() => onOpenUid(n.uid)} style={{
        display: "block", width: "100%", textAlign: "left", border: 0,
        background: n.uid === selectedUid ? "var(--vault-sunken)" : "transparent",
        borderBottom: "1px solid var(--vault-rule)", padding: "10px 16px", cursor: "pointer",
        fontFamily: "var(--font-sans)"
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
          <TypeDot type={n.type} size={8}/>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--vault-fg-muted)", letterSpacing: "0.04em", textTransform: "uppercase" }}>{n.type}</span>
          <span style={{ marginLeft: "auto", fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--vault-fg-faint)" }}>{n.updated}</span>
        </div>
        <div style={{ fontSize: 13, color: "var(--vault-fg)", fontWeight: n.uid === selectedUid ? 600 : 500, lineHeight: 1.3, marginBottom: 4 }}>{n.title}</div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--vault-fg-faint)" }}>{n.uid}</div>
      </button>
    ))}
  </div>
);

const LinksPanel = ({ node, vault, onOpenUid }) => {
  if (!node) return <Empty>No node selected.</Empty>;

  const outgoing = (node.relations || []).map(r => ({ ...r, target: vault.find(n => n.uid === r.uid) })).filter(r => r.target);
  const incoming = vault.filter(n => n.uid !== node.uid).flatMap(n =>
    (n.relations || []).filter(r => r.uid === node.uid).map(r => ({ source: n, type: r.type }))
  );

  const Group = ({ title, count, items, render }) => (
    <div style={{ borderBottom: "1px solid var(--vault-rule)" }}>
      <div style={{ padding: "12px 16px 6px", display: "flex", alignItems: "baseline", gap: 8 }}>
        <span style={{ fontFamily: "var(--font-sans)", fontSize: 10, fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--vault-fg-muted)" }}>{title}</span>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--vault-fg-faint)" }}>{count}</span>
      </div>
      <div style={{ paddingBottom: 8 }}>
        {items.length === 0 ? <Empty subtle>—</Empty> : items.map(render)}
      </div>
    </div>
  );

  return (
    <div>
      {/* header — current node */}
      <div style={{ padding: "12px 16px", background: "#fff", borderBottom: "1px solid var(--vault-rule)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
          <TypeDot type={node.type}/>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--vault-fg-muted)" }}>{node.type} · {node.uid}</span>
        </div>
        <div style={{ fontFamily: "var(--font-serif)", fontSize: 16, lineHeight: 1.3, color: "var(--vault-fg)" }}>{node.title}</div>
      </div>

      <Group title="Outgoing" count={outgoing.length} items={outgoing} render={(r, i) => (
        <RelationRow key={"o"+i} type={r.type} dir="→" target={r.target} onOpen={() => onOpenUid(r.target.uid)}/>
      )}/>
      <Group title="Incoming" count={incoming.length} items={incoming} render={(r, i) => (
        <RelationRow key={"i"+i} type={r.type} dir="←" target={r.source} onOpen={() => onOpenUid(r.source.uid)}/>
      )}/>
    </div>
  );
};

const RelationRow = ({ type, dir, target, onOpen }) => (
  <button onClick={onOpen} style={{
    display: "grid", gridTemplateColumns: "auto 1fr", gap: "0 10px",
    width: "100%", textAlign: "left", border: 0, background: "transparent",
    padding: "8px 16px", cursor: "pointer", fontFamily: "var(--font-sans)",
    alignItems: "center"
  }}>
    <TypeDot type={target.type} size={8}/>
    <div style={{ display: "flex", alignItems: "baseline", gap: 8, minWidth: 0 }}>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--vault-fg-muted)" }}>{dir}</span>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--vault-accent)", padding: "1px 5px", background: "var(--vault-sunken)", borderRadius: 2, flexShrink: 0, whiteSpace: "nowrap" }}>{type}</span>
      <span style={{ fontSize: 12, color: "var(--vault-fg)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{target.title}</span>
    </div>
  </button>
);

const Empty = ({ children, subtle }) => (
  <div style={{ padding: subtle ? "4px 16px 8px" : "32px 16px", fontFamily: "var(--font-sans)", fontSize: subtle ? 11 : 12, color: "var(--vault-fg-faint)", fontStyle: subtle ? "normal" : "italic", textAlign: subtle ? "left" : "center" }}>{children}</div>
);

window.RightRail = RightRail;
