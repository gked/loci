import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getHealth } from "../lib/api.js";

export function VaultRail({ active, onNav, nodes, activeTag, onTagSelect }) {
  const [tagFilter, setTagFilter] = useState("");

  // The version comes from the backend, which reads it out of pyproject.toml.
  // Keeping a literal here is what let the rail drift to a "v0.4" that existed
  // nowhere else in the project. Until the request lands there is no number to
  // show, so the roman year stands alone rather than flashing a wrong one.
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    staleTime: Infinity,
  });

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
      data-testid="rail-row"
      data-rail-id={id}
      data-active={active === id ? "true" : "false"}
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
      data-testid="rail-tag"
      data-tag={tag}
      data-active={activeTag === tag ? "true" : "false"}
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
        <span className="ver" data-testid="app-version" data-version={health?.version || ""}>
          {health?.version ? `v${health.version} · mmxxvi` : "mmxxvi"}
        </span>
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
            <div style={{ padding: "2px 8px 6px", position: "relative" }}>
              <input
                type="text"
                value={tagFilter}
                onChange={e => setTagFilter(e.target.value)}
                placeholder="filter tags…"
                aria-label="filter tags"
                style={{
                  width: "100%",
                  boxSizing: "border-box",
                  background: "transparent",
                  border: "none",
                  borderBottom: "1px solid var(--t-border)",
                  color: "var(--t-fg-mute)",
                  fontFamily: "var(--font-mono)",
                  fontSize: 10,
                  letterSpacing: "0.03em",
                  padding: "2px 14px 2px 0",
                  outline: "none",
                }}
              />
              {tagFilter && (
                <button
                  onClick={() => setTagFilter("")}
                  style={{
                    position: "absolute",
                    right: 8,
                    top: "50%",
                    transform: "translateY(-50%)",
                    background: "none",
                    border: "none",
                    padding: 0,
                    cursor: "pointer",
                    color: "var(--t-fg-faint)",
                    fontSize: 10,
                    lineHeight: 1,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                  aria-label="clear filter"
                >
                  ✕
                </button>
              )}
            </div>
            {tags
              .filter(([tag]) => tag.toLowerCase().includes(tagFilter.toLowerCase()))
              .map(([tag, count]) => (
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
        <div className="health" data-testid="rail-count" data-count={nodes.length}>
          vault · {nodes.length} loci
        </div>
        <div style={{ color: "var(--t-fg-faint)", fontSize: 9 }}>~/loci</div>
      </div>
    </aside>
  );
}
