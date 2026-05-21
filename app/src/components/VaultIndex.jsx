import { TypeDot } from "./TypeDot.jsx";
import { HeaderStrip } from "./HeaderStrip.jsx";
import { Meridian } from "./Meridian.jsx";
import { Corners } from "./Corners.jsx";

const FILTER_TYPES = ["all","project","topic","article","bookmark","conversation","procedure","entity","task","document","asset"];

function ToggleSwitch({ active, onToggle, label }) {
  return (
    <span
      onClick={onToggle}
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

export function VaultIndex({ nodes, selectedUid, onOpen, section, onNav, activeTag, onTagSelect, showArchived, onToggleArchived, showGhost, onToggleGhost }) {
  const activeFilter = section?.startsWith("t:") ? section.slice(2) : "all";
  const archivedCount = showArchived ? nodes.filter(n => n.state === "archived").length : 0;
  const ghostCount = showGhost ? nodes.filter(n => !n.path).length : 0;

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", position: "relative", minWidth: 0 }} className="canvas">
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
            <b>{nodes.length}</b> nodes · sorted by <b>updated</b> ↓
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
        {FILTER_TYPES.map((t) => (
          <span
            key={t}
            className="t-chip"
            onClick={() => onNav(t === "all" ? "all" : `t:${t}`)}
            style={{ cursor: "pointer", opacity: activeFilter === t ? 1 : 0.45 }}
          >
            {t !== "all" && <TypeDot type={t} size={6}/>}
            {t}
          </span>
        ))}
        {activeTag && (
          <>
            <span style={{ color: "var(--t-rule)", margin: "0 2px" }}>·</span>
            <span
              className="t-chip"
              onClick={() => onTagSelect(activeTag)}
              style={{ cursor: "pointer", opacity: 1, color: "var(--t-bronze)", display: "flex", alignItems: "center", gap: 4 }}
            >
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 9 }}>#</span>
              {activeTag}
              <span style={{ fontSize: 9, opacity: 0.7, marginLeft: 2 }}>×</span>
            </span>
          </>
        )}
        <span style={{ flex: 1 }}/>
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
        {nodes.map(n => {
          const isArchived = n.state === "archived";
          const isGhost = !n.path;
          return (
          <div
            key={n.uid}
            className={`list-row ${selectedUid === n.uid ? "selected" : ""}`}
            onClick={() => !isGhost && onOpen(n.uid)}
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
                  : n.type}
            </span>
            <span className="lr-uid">{n.uid}</span>
            <span className="lr-date">{(n.updated_at || "").slice(0, 10)}</span>
          </div>
          );
        })}
        {nodes.length === 0 && (
          <div style={{ padding: "48px 24px", textAlign: "center", fontFamily: "var(--font-display)", fontStyle: "italic", color: "var(--t-fg-faint)", fontSize: 14 }}>
            vacuum · no loci found
          </div>
        )}
      </div>
    </div>
  );
}
