import { useMemo } from "react";

export function VaultRail({ active, onNav, nodes, activeTag, onTagSelect }) {
  const tags = useMemo(() => {
    const counts = {};
    nodes.forEach(n => (n.tags || []).forEach(t => {
      counts[t] = (counts[t] || 0) + 1;
    }));
    return Object.entries(counts).sort((a, b) => b[1] - a[1]);
  }, [nodes]);

  const Row = ({ id, label, latin, icon, count }) => (
    <button
      className={`rail-row ${active === id ? "active" : ""}`}
      onClick={() => onNav(id)}
    >
      <span style={{ width: 14, height: 14, display: "inline-flex", alignItems: "center", justifyContent: "center", color: "var(--t-bronze)", fontSize: 13 }}>
        {icon}
      </span>
      <span style={{ flex: 1, display: "flex", flexDirection: "column", lineHeight: 1.05 }}>
        <span>{label}</span>
        {latin && (
          <span style={{ fontFamily: "var(--font-display)", fontStyle: "italic", fontSize: 9.5, color: "var(--t-fg-faint)", letterSpacing: "0.06em" }}>
            {latin}
          </span>
        )}
      </span>
      {count != null && (
        <span className="count">{String(count).padStart(3, "0")}</span>
      )}
    </button>
  );

  const TagRow = ({ tag, count }) => (
    <button
      className={`rail-row ${activeTag === tag ? "active" : ""}`}
      onClick={() => onTagSelect(tag)}
    >
      <span style={{ width: 14, height: 14, display: "inline-flex", alignItems: "center", justifyContent: "center", color: "var(--t-bronze)", fontSize: 10, opacity: 0.7 }}>
        #
      </span>
      <span style={{ flex: 1, fontFamily: "var(--font-mono)", fontSize: 10.5, letterSpacing: "0.03em" }}>
        {tag}
      </span>
      <span className="count">{String(count).padStart(3, "0")}</span>
    </button>
  );

  return (
    <aside className="rail">
      <div className="rail-head">
        <span className="wm">Loci</span>
        <span className="ver">v0.4 · mmxxvi</span>
      </div>

      <div style={{ padding: "8px 0", display: "flex", flexDirection: "column", overflowY: "auto", flex: 1 }}>
        <div className="rail-section">
          prima · primary <span className="roman">I</span>
        </div>
        <Row id="all"      label="All loci"  latin="omnia loca"  icon="∎" count={nodes.length}/>
        <Row id="recent"   label="Recent"    latin="recentia"    icon="↺"/>
        <Row id="graph"    label="Topology"  latin="topologia"   icon="◌"/>

        {tags.length > 0 && (
          <>
            <div className="rail-section">
              notae · tags <span className="roman">II</span>
            </div>
            {tags.map(([tag, count]) => (
              <TagRow key={tag} tag={tag} count={count}/>
            ))}
          </>
        )}

        <div className="rail-section">
          instrumenta · tools <span className="roman">{tags.length > 0 ? "III" : "II"}</span>
        </div>
        <Row id="cmd"      label="Command"   latin="praeceptum"  icon="⌘"/>
        <Row id="settings" label="Settings"  latin="calibratio"  icon="⚙"/>
      </div>

      <div className="rail-foot">
        <div className="health">
          vault · {nodes.length} loci
        </div>
        <div style={{ color: "var(--t-fg-faint)", fontSize: 9 }}>~/loci</div>
      </div>
    </aside>
  );
}
