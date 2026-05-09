import { useState } from "react";
import { TypeDot } from "./TypeDot.jsx";
import { Icon } from "./Icon.jsx";
import { TYPES } from "../constants.js";

export function RightRail({ section, onNav, nodes, recentNodes, neighbors, selectedUid, onOpenUid, onOpenGraph }) {
  const [tab, setTab] = useState("loci");

  // Client-side filtering for LociPanel
  const filteredNodes = section === "recent" ? recentNodes
    : section.startsWith("t:") ? nodes.filter(n => n.type === section.slice(2))
    : section.startsWith("#") ? nodes.filter(n => (n.tags || []).includes(section.slice(1)))
    : nodes;

  const sectionLabel = section === "all" ? "All loci"
    : section === "recent" ? "Recently updated"
    : section.startsWith("t:") ? section.slice(2)
    : section.startsWith("#") ? section
    : section;

  const selected = nodes.find(n => n.uid === selectedUid) || recentNodes.find(n => n.uid === selectedUid);

  return (
    <aside style={{
      width: 360, flexShrink: 0, borderLeft: "1px solid var(--vault-rule)",
      background: "var(--vault-bg)", display: "flex", flexDirection: "column", minHeight: 0,
    }}>
      {/* tabs */}
      <div style={{ display: "flex", borderBottom: "1px solid var(--vault-rule)", background: "#fff", flexShrink: 0 }}>
        {[["vault", "Vault"], ["loci", "Loci"], ["links", "Links"]].map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)} style={{
            flex: 1, padding: "12px 0", border: 0, background: "transparent",
            fontFamily: "var(--font-sans)", fontSize: 12,
            fontWeight: tab === id ? 600 : 400,
            color: tab === id ? "var(--vault-fg)" : "var(--vault-fg-muted)",
            borderBottom: "2px solid " + (tab === id ? "var(--vault-fg)" : "transparent"),
            cursor: "pointer", letterSpacing: "0.02em",
            display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6,
          }}>
            {label}
            {id === "links" && selected && (
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--vault-fg-muted)", padding: "1px 5px", background: "var(--vault-sunken)", borderRadius: 8 }}>
                {neighbors.length}
              </span>
            )}
            {id === "loci" && (
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--vault-fg-muted)", padding: "1px 5px", background: "var(--vault-sunken)", borderRadius: 8 }}>
                {filteredNodes.length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* tab content */}
      <div style={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
        {tab === "vault" && (
          <VaultPanel section={section} onNav={onNav} nodes={nodes} onOpenGraph={onOpenGraph} />
        )}
        {tab === "loci" && (
          <LociPanel sectionLabel={sectionLabel} nodes={filteredNodes} selectedUid={selectedUid} onOpenUid={onOpenUid} />
        )}
        {tab === "links" && (
          <LinksPanel selected={selected} neighbors={neighbors} onOpenUid={onOpenUid} />
        )}
      </div>

      {/* footer */}
      <div style={{
        padding: "10px 14px", borderTop: "1px solid var(--vault-rule)",
        display: "flex", alignItems: "center", gap: 8,
        fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--vault-fg-muted)", flexShrink: 0,
      }}>
        <Icon name="settings" size={11} />
        <span>{nodes.length} loci</span>
      </div>
    </aside>
  );
}

function VaultPanel({ section, onNav, nodes, onOpenGraph }) {
  const counts = {};
  TYPES.forEach(([t]) => { counts[t] = nodes.filter(n => n.type === t).length; });

  const Row = ({ id, icon, label, count, type, onClick }) => (
    <button onClick={onClick || (() => onNav(id))} style={{
      display: "flex", alignItems: "center", gap: 10, padding: "7px 14px",
      border: 0, background: section === id ? "var(--vault-sunken)" : "transparent",
      color: "var(--vault-fg)", fontFamily: "var(--font-sans)", fontSize: 13,
      fontWeight: section === id ? 600 : 400, cursor: "pointer", textAlign: "left", width: "100%",
    }}>
      {type ? <TypeDot type={type} /> : <Icon name={icon} size={14} />}
      <span style={{ flex: 1 }}>{label}</span>
      {count != null && (
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--vault-fg-faint)" }}>{count}</span>
      )}
    </button>
  );

  const Heading = ({ children }) => (
    <div style={{ padding: "14px 14px 4px", fontSize: 10, fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--vault-fg-muted)" }}>
      {children}
    </div>
  );

  return (
    <div style={{ padding: "8px 0" }}>
      <Row id="all" icon="inbox" label="All loci" count={nodes.length} />
      <Row id="recent" icon="enter" label="Recent" />
      <Row id="graph" icon="graph" label="Topology" onClick={onOpenGraph} />
      <Heading>Types</Heading>
      {TYPES.filter(([t]) => counts[t] > 0).map(([t]) => (
        <Row key={t} id={"t:" + t} type={t} label={t} count={counts[t]} />
      ))}
    </div>
  );
}

function LociPanel({ sectionLabel, nodes, selectedUid, onOpenUid }) {
  return (
    <div>
      <div style={{
        padding: "12px 16px 8px", display: "flex", alignItems: "baseline", gap: 8,
        position: "sticky", top: 0, background: "var(--vault-bg)", zIndex: 1,
        borderBottom: "1px solid var(--vault-rule)",
      }}>
        <span style={{ fontFamily: "var(--font-sans)", fontSize: 10, fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--vault-fg-muted)" }}>
          {sectionLabel}
        </span>
      </div>
      {nodes.map(n => (
        <button key={n.uid} onClick={() => onOpenUid(n.uid)} style={{
          display: "block", width: "100%", textAlign: "left", border: 0,
          background: n.uid === selectedUid ? "var(--vault-sunken)" : "transparent",
          borderBottom: "1px solid var(--vault-rule)", padding: "10px 16px", cursor: "pointer",
          fontFamily: "var(--font-sans)",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
            <TypeDot type={n.type} size={8} />
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--vault-fg-muted)", letterSpacing: "0.04em", textTransform: "uppercase" }}>{n.type}</span>
            <span style={{ marginLeft: "auto", fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--vault-fg-faint)" }}>{n.updated_at?.slice(0, 10)}</span>
          </div>
          <div style={{ fontSize: 13, color: "var(--vault-fg)", fontWeight: n.uid === selectedUid ? 600 : 500, lineHeight: 1.3, marginBottom: 4 }}>
            {n.title}
          </div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--vault-fg-faint)" }}>{n.uid}</div>
        </button>
      ))}
      {nodes.length === 0 && (
        <div style={{ padding: "32px 16px", fontFamily: "var(--font-sans)", fontSize: 12, color: "var(--vault-fg-faint)", fontStyle: "italic", textAlign: "center" }}>
          No loci in this section.
        </div>
      )}
    </div>
  );
}

function LinksPanel({ selected, neighbors, onOpenUid }) {
  if (!selected) {
    return (
      <div style={{ padding: "32px 16px", fontFamily: "var(--font-sans)", fontSize: 12, color: "var(--vault-fg-faint)", fontStyle: "italic", textAlign: "center" }}>
        No node selected.
      </div>
    );
  }

  const outgoing = neighbors.filter(n => n.direction === "out");
  const incoming = neighbors.filter(n => n.direction === "in");

  return (
    <div>
      {/* header */}
      <div style={{ padding: "12px 16px", background: "#fff", borderBottom: "1px solid var(--vault-rule)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
          <TypeDot type={selected.type} />
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--vault-fg-muted)" }}>
            {selected.type} · {selected.uid}
          </span>
        </div>
        <div style={{ fontFamily: "var(--font-serif)", fontSize: 16, lineHeight: 1.3, color: "var(--vault-fg)" }}>
          {selected.title}
        </div>
      </div>

      <RelGroup title="Outgoing" items={outgoing} dir="→" onOpenUid={onOpenUid} />
      <RelGroup title="Incoming" items={incoming} dir="←" onOpenUid={onOpenUid} />
    </div>
  );
}

function RelGroup({ title, items, dir, onOpenUid }) {
  return (
    <div style={{ borderBottom: "1px solid var(--vault-rule)" }}>
      <div style={{ padding: "12px 16px 6px", display: "flex", alignItems: "baseline", gap: 8 }}>
        <span style={{ fontFamily: "var(--font-sans)", fontSize: 10, fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--vault-fg-muted)" }}>
          {title}
        </span>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--vault-fg-faint)" }}>{items.length}</span>
      </div>
      <div style={{ paddingBottom: 8 }}>
        {items.length === 0 ? (
          <div style={{ padding: "4px 16px 8px", fontFamily: "var(--font-sans)", fontSize: 11, color: "var(--vault-fg-faint)" }}>—</div>
        ) : items.map((r, i) => (
          <button key={i} onClick={() => onOpenUid(r.uid)} style={{
            display: "grid", gridTemplateColumns: "auto 1fr", gap: "0 10px",
            width: "100%", textAlign: "left", border: 0, background: "transparent",
            padding: "8px 16px", cursor: "pointer", fontFamily: "var(--font-sans)",
            alignItems: "center",
          }}>
            <TypeDot type={r.type} size={8} />
            <div style={{ display: "flex", alignItems: "baseline", gap: 8, minWidth: 0 }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--vault-fg-muted)" }}>{dir}</span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--vault-accent)", padding: "1px 5px", background: "var(--vault-sunken)", borderRadius: 2, flexShrink: 0, whiteSpace: "nowrap" }}>
                {r.rel_type}
              </span>
              <span style={{ fontSize: 12, color: "var(--vault-fg)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {r.title}
              </span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
