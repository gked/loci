import { TypeDot } from "./TypeDot.jsx";
import { HeaderStrip } from "./HeaderStrip.jsx";
import { Meridian } from "./Meridian.jsx";
import { Corners } from "./Corners.jsx";

const FILTER_TYPES = ["all","project","topic","article","bookmark","conversation","procedure","entity","task","document","asset"];

export function VaultIndex({ nodes, selectedUid, onOpen, section, onNav }) {
  const activeFilter = section?.startsWith("t:") ? section.slice(2) : "all";

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
        telemetry={<><b>{nodes.length}</b> nodes · sorted by <b>updated</b> ↓</>}
        right={
          <span className="tel">⌘K to search</span>
        }
      />

      {/* filter strip */}
      <div style={{ padding: "8px 24px", display: "flex", alignItems: "center", gap: 10, borderBottom: "1px solid var(--t-rule-soft)", flexShrink: 0 }}>
        <span className="smcaps">filter</span>
        {FILTER_TYPES.slice(0, 7).map((t, i) => (
          <span
            key={t}
            className="t-chip"
            onClick={() => onNav(t === "all" ? "all" : `t:${t}`)}
            style={{ cursor: "pointer", opacity: activeFilter === t ? 1 : 0.55 }}
          >
            {t !== "all" && <TypeDot type={t} size={6}/>}
            {t}
          </span>
        ))}
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
        {nodes.map(n => (
          <div
            key={n.uid}
            className={`list-row ${selectedUid === n.uid ? "selected" : ""}`}
            onClick={() => onOpen(n.uid)}
          >
            <TypeDot type={n.type}/>
            <div>
              <div className="lr-title">{n.title}</div>
              {n.tags && n.tags.length > 0 && (
                <div style={{ marginTop: 3, display: "flex", gap: 6 }}>
                  {n.tags.slice(0, 3).map(t => (
                    <span key={t} style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--t-fg-faint)", letterSpacing: "0.04em" }}>
                      #{t}
                    </span>
                  ))}
                </div>
              )}
            </div>
            <span className="lr-type">{n.type}</span>
            <span className="lr-uid">{n.uid}</span>
            <span className="lr-date">{(n.updated_at || "").slice(0, 10)}</span>
          </div>
        ))}
        {nodes.length === 0 && (
          <div style={{ padding: "48px 24px", textAlign: "center", fontFamily: "var(--font-display)", fontStyle: "italic", color: "var(--t-fg-faint)", fontSize: 14 }}>
            vacuum · no loci found
          </div>
        )}
      </div>
    </div>
  );
}
