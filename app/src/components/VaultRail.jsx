import { useQuery } from "@tanstack/react-query";
import { getHealth } from "../lib/api.js";

function Row({ id, label, latin, icon, count, active, onNav }) {
  return (
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
}

// One row under an expanded type: a subtype ("s:<name>") or a user-defined type ("u:<name>").
function ChildRow({ kind, name, testid, childCounts, activeChild, onChildSelect }) {
  const key = `${kind}:${name}`;
  const count = childCounts[key] || 0;
  const on = activeChild === key;
  return (
    <button
      className={`rail-row ${on ? "active" : ""}`}
      onClick={() => onChildSelect(key)}
      data-testid={testid}
      data-subtype={kind === "s" ? name : undefined}
      data-usertype={kind === "u" ? name : undefined}
      data-active={on ? "true" : "false"}
      data-count={count}
      style={{ opacity: on || count ? 1 : 0.4, paddingLeft: 28 }}
    >
      <span style={{ flex: 1, fontFamily: "var(--font-mono)", fontSize: 10.5, letterSpacing: "0.03em" }}>
        {name}
      </span>
      <span className="count">{String(count).padStart(3, "0")}</span>
    </button>
  );
}

function GroupLabel({ children }) {
  return (
    <div style={{ padding: "6px 14px 2px 28px", fontFamily: "var(--font-display)", fontStyle: "italic", fontSize: 9.5, color: "var(--t-fg-faint)", letterSpacing: "0.06em" }}>
      {children}
    </div>
  );
}

// A main type's group: collapsed until that type is chosen at the top (or here).
// Clicking the open type's header clears the type, like its chip in the top bar.
function TypeGroup({ type, userTypes, activeType, onNav, ...child }) {
  const open = activeType === type.name;
  const mine = (type.subtypes || []);
  const yours = open ? userTypes : [];
  const bodyId = `rail-group-${type.name}`;
  return (
    <div data-testid="rail-type-group" data-type={type.name} data-open={open ? "true" : "false"}>
      <button
        className={`rail-row ${open ? "active" : ""}`}
        onClick={() => onNav(open ? "all" : `t:${type.name}`)}
        data-testid="rail-type"
        data-type={type.name}
        data-active={open ? "true" : "false"}
        aria-expanded={open}
        aria-controls={open ? bodyId : undefined}
      >
        <span style={{ width: 14, display: "inline-flex", justifyContent: "center", color: "var(--t-bronze)", fontSize: 10 }}>
          {open ? "▾" : "▸"}
        </span>
        <span style={{ flex: 1 }}>{type.name}</span>
      </button>
      {open && (
        <div id={bodyId}>
          {mine.length > 0 && (
            <div data-testid="subtype-strip">
              <GroupLabel>subtypes</GroupLabel>
              {mine.map(st => <ChildRow key={st} kind="s" name={st} testid="subtype-filter" {...child}/>)}
            </div>
          )}
          {yours.length > 0 && (
            <div data-testid="usertype-strip">
              <GroupLabel>yours</GroupLabel>
              {yours.map(name => <ChildRow key={name} kind="u" name={name} testid="usertype-filter" {...child}/>)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function VaultRail({ active, onNav, nodes, types = [], userTypes = [], activeType, childCounts = {}, activeChild, onChildSelect }) {
  // The version comes from the backend, which reads it out of pyproject.toml.
  // Keeping a literal here is what let the rail drift to a "v0.4" that existed
  // nowhere else in the project. Until the request lands there is no number to
  // show, so the roman year stands alone rather than flashing a wrong one.
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    staleTime: Infinity,
    // The version never changes, but the history state can: a write that could
    // not be recorded turns it to "error" while the page is open.
    refetchInterval: 30000,
    refetchIntervalInBackground: false,
  });
  const history = health?.history;

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
        <Row active={active} onNav={onNav} id="all"      label="All loci"  latin="omnia loca"  icon="∎" count={nodes.length}/>
        <Row active={active} onNav={onNav} id="recent"   label="Recent"    latin="recentia"    icon="↺"/>
        <Row active={active} onNav={onNav} id="graph"    label="Topology"  latin="topologia"   icon="◌"/>

        {types.length > 0 && (
          <>
            <div className="rail-section">
              genera · types <span className="roman">II</span>
            </div>
            {types.map(t => (
              <TypeGroup key={t.name} type={t} userTypes={userTypes} activeType={activeType} onNav={onNav}
                childCounts={childCounts} activeChild={activeChild} onChildSelect={onChildSelect}/>
            ))}
          </>
        )}

        <div className="rail-section">
          instrumenta · tools <span className="roman">{types.length > 0 ? "III" : "II"}</span>
        </div>
        <Row active={active} onNav={onNav} id="cmd"      label="Command"   latin="praeceptum"  icon="⌘"/>
        <Row active={active} onNav={onNav} id="settings" label="Settings"  latin="calibratio"  icon="⚙"/>
      </div>

      <div className="rail-foot">
        <div className="health" data-testid="rail-count" data-count={nodes.length}>
          vault · {nodes.length} loci
        </div>
        {history && history.state !== "unknown" && (
          <div className="history" data-testid="history-state" data-state={history.state}
               title={history.detail || undefined}>
            historia · {history.state}
          </div>
        )}
        <div style={{ color: "var(--t-fg-faint)", fontSize: 9 }}>~/loci</div>
      </div>
    </aside>
  );
}
