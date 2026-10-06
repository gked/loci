import { useState } from "react";
import { TypeDot } from "./TypeDot.jsx";
import { HeaderStrip } from "./HeaderStrip.jsx";
import { Meridian } from "./Meridian.jsx";
import { Corners } from "./Corners.jsx";

// Shown until /api/types answers; after that the registry's order wins.
const FALLBACK_TYPES = ["project","topic","article","bookmark","conversation","procedure","entity","task","document","asset","log"];

function ToggleSwitch({ active, onToggle, label }) {
  return (
    <span
      onClick={onToggle}
      data-testid={`toggle-${label}`}
      data-active={active ? "true" : "false"}
      style={{
        cursor: "pointer",
        display: "flex", alignItems: "center", gap: 5,
        fontFamily: "var(--font-mono)", fontSize: 9.5,
        letterSpacing: "0.08em", textTransform: "uppercase",
        color: active ? "var(--t-bronze)" : "var(--t-fg-faint)",
        opacity: active ? 1 : 0.5,
        userSelect: "none",
      }}
    >
      <span style={{
        width: 22, height: 12, borderRadius: 6,
        background: active ? "var(--t-bronze)" : "transparent",
        border: `1px solid ${active ? "var(--t-bronze)" : "var(--t-rule)"}`,
        position: "relative", flexShrink: 0, transition: "background 0.15s, border-color 0.15s",
      }}>
        <span style={{
          position: "absolute", top: 2, left: active ? 10 : 2,
          width: 6, height: 6, borderRadius: "50%",
          background: active ? "var(--t-bg)" : "var(--t-rule)",
          transition: "left 0.15s, background 0.15s",
        }}/>
      </span>
      {label}
    </span>
  );
}

export function VaultIndex({ nodes, selectedUid, onOpen, section, onNav, types = [], showArchived, onToggleArchived, showGhost, onToggleGhost }) {
  const [filterQ, setFilterQ] = useState("");
  const activeFilter = section?.startsWith("t:") ? section.slice(2) : "all";
  const filterTypes = ["all", ...(types.length ? types.map(t => t.name) : FALLBACK_TYPES)];
  const archivedCount = showArchived ? nodes.filter(n => n.state === "archived").length : 0;
  const ghostCount = showGhost ? nodes.filter(n => !n.path).length : 0;

  const q = filterQ.trim().toLowerCase();
  const displayNodes = q
    ? nodes.filter(n =>
        n.uid?.toLowerCase().includes(q) ||
        n.title?.toLowerCase().includes(q)
      )
    : nodes;

  return (
    <div
      style={{ flex: 1, display: "flex", flexDirection: "column", position: "relative", minWidth: 0 }}
      className="canvas"
      data-testid="vault-index"
    >
      <Meridian visible={false}/>
      <Corners
        bl={{ label: "focus · selectum", value: selectedUid || "—" }}
        br={{ label: "gradus · zoom", value: "i · 100%" }}
      />

      <HeaderStrip
        label="All loci"
        latin="omnia loca"
        telemetry={
          <>
            <b>{q ? displayNodes.length : nodes.length}</b>{q ? ` of ${nodes.length}` : ""} nodes · sorted by <b>updated</b> ↓
            {showArchived && archivedCount > 0 && (
              <span style={{ opacity: 0.55 }}> · <b>{archivedCount}</b> archived</span>
            )}
            {showGhost && ghostCount > 0 && (
              <span style={{ opacity: 0.55 }}> · <b>{ghostCount}</b> ghost</span>
            )}
          </>
        }
        right={
          <span className="tel">⌘K to search</span>
        }
      />

      {/* filter strip */}
      <div style={{ padding: "8px 24px", display: "flex", alignItems: "center", gap: 10, borderBottom: "1px solid var(--t-rule-soft)", flexShrink: 0, flexWrap: "wrap" }}>
        <span className="smcaps">type</span>
        {filterTypes.map((t) => (
          <span
            key={t}
            className="t-chip type-chip"
            onClick={() => onNav(t === "all" ? "all" : `t:${t}`)}
            data-testid="type-filter"
            data-type={t}
            data-active={activeFilter === t ? "true" : "false"}
            style={{ cursor: "pointer" }}
          >
            {t !== "all" && <TypeDot type={t} size={6}/>}
            {t}
          </span>
        ))}
        <span style={{ flex: 1 }}/>
        <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
          <input
            value={filterQ}
            onChange={e => setFilterQ(e.target.value)}
            placeholder="filter by uid or title…"
            className="t-input"
            style={{ fontSize: 11, padding: "3px 22px 3px 8px", width: 180 }}
          />
          {filterQ && (
            <button
              onClick={() => setFilterQ("")}
              aria-label="Clear filter"
              style={{
                position: "absolute", right: 6,
                fontFamily: "var(--font-mono)", fontSize: 10,
                color: "var(--t-fg-faint)", cursor: "pointer", lineHeight: 1,
                background: "none", border: "none", padding: 0,
              }}
            >×</button>
          )}
        </div>
        <ToggleSwitch active={showGhost} onToggle={onToggleGhost} label="ghost"/>
        <ToggleSwitch active={showArchived} onToggle={onToggleArchived} label="archived"/>
      </div>

      {/* column headers */}
      <div style={{
        display: "grid", gridTemplateColumns: "18px 1fr 90px 110px 80px",
        gap: 14, padding: "8px 24px",
        borderBottom: "1px solid var(--t-rule)",
        fontFamily: "var(--font-mono)", fontSize: 9.5, color: "var(--t-bronze)",
        letterSpacing: "0.12em", textTransform: "uppercase", flexShrink: 0,
      }}>
        <span/>
        <span>title <span style={{ fontFamily: "var(--font-display)", fontStyle: "italic", color: "var(--t-bronze-d)", letterSpacing: "0.04em", textTransform: "lowercase" }}>· titulus</span></span>
        <span>type</span>
        <span>uid</span>
        <span>updated</span>
      </div>

      <div style={{ flex: 1, minHeight: 0, overflowY: "auto" }}>
        {displayNodes.map(n => {
          const isArchived = n.state === "archived";
          const isGhost = !n.path;
          return (
          <div
            key={n.uid}
            className={`list-row ${selectedUid === n.uid ? "selected" : ""}`}
            onClick={() => !isGhost && onOpen(n.uid)}
            data-testid="node-row"
            data-uid={n.uid}
            data-state={isGhost ? "ghost" : isArchived ? "archived" : "active"}
            style={isGhost ? { opacity: 0.35, cursor: "default" } : isArchived ? { opacity: 0.45 } : undefined}
          >
            <TypeDot type={n.type}/>
            <div>
              <div className="lr-title" style={isArchived ? { textDecoration: "line-through", textDecorationColor: "var(--t-fg-faint)" } : undefined}>
                {isGhost ? <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.06em", color: "var(--t-fg-faint)", fontStyle: "italic" }}>missing node</span> : n.title}
              </div>
              {!isGhost && n.tags && n.tags.length > 0 && (
                <div style={{ marginTop: 3, display: "flex", gap: 6 }}>
                  {n.tags.slice(0, 3).map(t => (
                    <span key={t} style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--t-fg-faint)", letterSpacing: "0.04em" }}>
                      #{t}
                    </span>
                  ))}
                </div>
              )}
            </div>
            <span className="lr-type">
              {isGhost
                ? <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--t-fg-faint)" }}>ghost</span>
                : isArchived
                  ? <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--t-fg-faint)" }}>archived</span>
                  : <>
                      {n.type}
                      {n.subtype && (
                        <span data-testid="row-subtype" style={{ display: "block", fontFamily: "var(--font-mono)", fontSize: 9, letterSpacing: "0.04em", color: "var(--t-fg-faint)" }}>
                          {n.subtype}
                        </span>
                      )}
                    </>}
            </span>
            <span className="lr-uid">{n.uid}</span>
            <span className="lr-date">{(n.updated_at || "").slice(0, 10)}</span>
          </div>
          );
        })}
        {displayNodes.length === 0 && (
          <div data-testid="index-empty" style={{ padding: "48px 24px", textAlign: "center", fontFamily: "var(--font-display)", fontStyle: "italic", color: "var(--t-fg-faint)", fontSize: 14 }}>
            {q ? `vacuum · no match for "${filterQ}"` : "vacuum · no loci found"}
          </div>
        )}
      </div>
    </div>
  );
}
