import { TypeDot } from "./TypeDot.jsx";

const T_LATIN = {
  project: "negotium", task: "labor", document: "documentum",
  entity: "persona", conversation: "colloquium", article: "articulus",
  bookmark: "signum", procedure: "ratio", topic: "argumentum",
  event: "eventus", asset: "res",
};

const TYPES = [
  "project","task","document","entity","conversation",
  "article","bookmark","procedure","topic","event","asset",
];

export function VaultRail({ active, onNav, nodes }) {
  const counts = {};
  TYPES.forEach(t => { counts[t] = nodes.filter(n => n.type === t).length; });

  const Row = ({ id, type, label, count, latin, icon }) => (
    <button
      className={`rail-row ${active === id ? "active" : ""}`}
      onClick={() => onNav(id)}
    >
      {type
        ? <TypeDot type={type} size={8}/>
        : <span style={{ width: 14, height: 14, display: "inline-flex", alignItems: "center", justifyContent: "center", color: "var(--t-bronze)", fontSize: 13 }}>{icon}</span>
      }
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

        <div className="rail-section">
          genera · types <span className="roman">II</span>
        </div>
        {TYPES.filter(t => counts[t] > 0).map(t => (
          <Row key={t} id={`t:${t}`} type={t} label={t} latin={T_LATIN[t]} count={counts[t]}/>
        ))}

        <div className="rail-section">
          instrumenta · tools <span className="roman">III</span>
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
