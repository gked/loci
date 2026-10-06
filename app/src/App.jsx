import { useState, useEffect, useCallback, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { VaultRail } from "./components/VaultRail.jsx";
import { VaultIndex } from "./components/VaultIndex.jsx";
import { NodeDetail } from "./components/NodeDetail.jsx";
import { GraphView } from "./components/GraphView.jsx";
import { CommandPalette } from "./components/CommandPalette.jsx";
import { getNodes, getNode, getNodeNeighbors, getRecentNodes, getGraph, getTypes } from "./lib/api.js";

export default function App() {
  const [selectedUid, setSelectedUid] = useState(null);
  const [section, setSection] = useState("all");
  // The rail row narrowing a type view: "s:<subtype>" or "u:<user type>", or null.
  const [activeChild, setActiveChild] = useState(null);
  const [cmdOpen, setCmdOpen] = useState(false);
  const [paper, setPaper] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [showGhost, setShowGhost] = useState(false);

  // Always fetch all nodes (including archived + ghost); toggles filter client-side
  const { data: allNodesRaw = [], isError: nodesError } = useQuery({
    queryKey: ["nodes"],
    queryFn: () => getNodes({ state: "all" }),
    staleTime: 30_000,
  });

  // Type vocabulary from the registry — the type chips and, per type, the subtype chips.
  const { data: types = [] } = useQuery({
    queryKey: ["types"],
    queryFn: getTypes,
    staleTime: 30_000,
  });

  // Active-only subset for the rail's total count — excludes archived regardless of toggle
  const allNodes = allNodesRaw.filter(n => n.state !== "archived" && n.path);

  // Recent nodes for "recent" section
  const { data: recentNodes = [] } = useQuery({
    queryKey: ["nodes/recent"],
    queryFn: getRecentNodes,
    staleTime: 30_000,
  });

  // Selected node detail
  const { data: nodeData } = useQuery({
    queryKey: ["node", selectedUid],
    queryFn: () => getNode(selectedUid),
    enabled: !!selectedUid,
    staleTime: 30_000,
  });

  // Neighbors for the selected node
  const { data: neighbors = [] } = useQuery({
    queryKey: ["neighbors", selectedUid],
    queryFn: () => getNodeNeighbors(selectedUid),
    enabled: !!selectedUid,
    staleTime: 30_000,
  });

  // Graph data (only when on topology section)
  const { data: rawGraphData } = useQuery({
    queryKey: ["graph"],
    queryFn: getGraph,
    enabled: section === "graph",
    staleTime: 60_000,
  });

  // Keyboard shortcuts
  useEffect(() => {
    const onKey = (e) => {
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setCmdOpen(o => !o);
        return;
      }
      if (e.key === "g" && !e.metaKey && !e.ctrlKey && !e.altKey) {
        setSection(s => s === "graph" ? "all" : "graph");
        return;
      }
      if (e.key === "r" && !e.metaKey && !e.ctrlKey) {
        setPaper(p => !p);
        return;
      }
      if (e.key === "Escape") {
        if (cmdOpen) { setCmdOpen(false); return; }
        if (section === "node") { setSection("all"); return; }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [cmdOpen, section]);

  // Flatten API node response for NodeDetail
  const selectedNode = nodeData ? {
    uid: nodeData.uid,
    ...nodeData.frontmatter,
    body: nodeData.body,
    asset: nodeData.asset || null,
  } : null;

  // Normalise graph data edges: rel_type → type for GraphView
  const graphData = rawGraphData ? {
    nodes: rawGraphData.nodes,
    edges: rawGraphData.edges.map(e => ({ source: e.source, target: e.target, type: e.rel_type })),
  } : null;

  const handleOpenNode = (uid) => {
    setSelectedUid(uid);
    setSection("node");
    setCmdOpen(false);
  };

  const handleNav = (id) => {
    if (id === "cmd") { setCmdOpen(true); return; }
    // A rail child only means something within its type, so leaving the type drops it.
    if (id !== section) setActiveChild(null);
    setSection(id);
  };

  const handleChildSelect = useCallback((key) => {
    setActiveChild(prev => prev === key ? null : key);
  }, []);

  // Main types head the top bar; user-defined types extend one and live in the rail under it.
  const mainTypes = useMemo(() => types.filter(t => !t.extends), [types]);
  const activeType = section.startsWith("t:") ? section.slice(2) : null;

  // A user type has no chip of its own: any route to it (palette, node detail, a
  // stale link) lands on its root main type narrowed to it. Runs once the types
  // have loaded, so a link followed before that resolves too; a type that no
  // longer exists falls back to "all".
  useEffect(() => {
    if (!types.length || !activeType) return;
    const t = types.find(x => x.name === activeType);
    if (!t) { setSection("all"); return; }
    if (!t.extends) return;
    let root = t;
    const seen = new Set([t.name]);
    while (root.extends && !seen.has(root.extends)) {
      const parent = types.find(x => x.name === root.extends);
      if (!parent) break;
      root = parent;
      seen.add(root.name);
    }
    setSection(`t:${root.name}`);
    setActiveChild(`u:${t.name}`);
  }, [types, activeType]);

  // Every user type below the active one, however deeply it extends.
  const userTypes = useMemo(() => {
    if (!activeType) return [];
    const found = [];
    const seen = new Set([activeType]);
    let level = [activeType];
    while (level.length) {
      const next = types.filter(t => t.extends && level.includes(t.extends) && !seen.has(t.name)).map(t => t.name);
      next.forEach(n => seen.add(n));
      found.push(...next);
      level = next;
    }
    return found;
  }, [types, activeType]);

  // Determine which nodes to show in VaultIndex
  const visibleNodes = useMemo(
    () => showArchived ? allNodesRaw : allNodesRaw.filter(n => n.state !== "archived"),
    [showArchived, allNodesRaw]);
  const baseNodes = useMemo(() => {
    if (section === "recent") return recentNodes;
    if (!activeType) return visibleNodes;
    const family = new Set([activeType, ...userTypes]);
    return visibleNodes.filter(n => family.has(n.type));
  }, [section, recentNodes, visibleNodes, activeType, userTypes]);
  // Rail counts reflect what the type filter left, then the chosen row narrows further.
  // A rail child only applies inside a type view: every path back to "all"
  // (node back, Escape, graph) would otherwise keep narrowing the
  // index with no row on screen to show why.
  const childCounts = useMemo(() => {
    const counts = {};
    for (const n of baseNodes) {
      if (n.subtype) counts[`s:${n.subtype}`] = (counts[`s:${n.subtype}`] || 0) + 1;
      if (activeType && n.type !== activeType) counts[`u:${n.type}`] = (counts[`u:${n.type}`] || 0) + 1;
    }
    return counts;
  }, [baseNodes, activeType]);
  const effectiveChild = activeType ? activeChild : null;
  const withChild = !effectiveChild ? baseNodes
    : effectiveChild.startsWith("s:") ? baseNodes.filter(n => n.subtype === effectiveChild.slice(2))
    : baseNodes.filter(n => n.type === effectiveChild.slice(2));
  const indexNodes = showGhost ? withChild : withChild.filter(n => n.path);

  // Active rail id (for VaultIndex sections we highlight the specific type/all/recent)
  const railActive = section;

  return (
    <div
      data-motion="subtle"
      data-density="regular"
      style={{
        height: "100vh", width: "100%", display: "flex", minHeight: 0, overflow: "hidden",
        "--flow-dur": "3s",
        "--bezel-dur": "240s",
        "--meridian-opacity": 0.35,
      }}
    >
      <VaultRail
        active={railActive}
        onNav={handleNav}
        nodes={allNodes}
        types={mainTypes}
        userTypes={userTypes}
        activeType={activeType}
        childCounts={childCounts}
        activeChild={effectiveChild}
        onChildSelect={handleChildSelect}
      />

      {/* main content area */}
      <div style={{ flex: 1, position: "relative", minWidth: 0, minHeight: 0, display: "flex", flexDirection: "column" }}>
        {nodesError && (
          <div data-testid="api-error" style={{
            padding: "10px 20px", background: "rgba(192,57,43,0.15)",
            borderBottom: "1px solid rgba(192,57,43,0.4)", flexShrink: 0,
            fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--vault-danger)",
            display: "flex", alignItems: "center", gap: 10,
          }}>
            <span>⚠</span>
            <span>Cannot reach API — is <code>make dev-api</code> running?</span>
          </div>
        )}
        <div style={{ flex: 1, position: "relative", minWidth: 0, minHeight: 0, display: "flex" }}>
        {/* Screens */}
        {(section === "all" || section === "recent" || section.startsWith("t:")) && (
          <VaultIndex
            nodes={indexNodes}
            selectedUid={selectedUid}
            onOpen={handleOpenNode}
            section={section}
            onNav={handleNav}
            types={mainTypes}
            showArchived={showArchived}
            onToggleArchived={() => setShowArchived(v => !v)}
            showGhost={showGhost}
            onToggleGhost={() => setShowGhost(v => !v)}
          />
        )}

        {section === "node" && (
          <NodeDetail
            node={selectedNode}
            neighbors={neighbors}
            onOpenUid={handleOpenNode}
            onBack={() => setSection("all")}
            onShowTopology={() => setSection("graph")}
            paper={paper}
          />
        )}

        {section === "graph" && graphData && (
          <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
            <div style={{
              height: 46, display: "flex", alignItems: "center", padding: "0 20px",
              background: "rgba(6,9,20,0.9)", borderBottom: "1px solid var(--t-rule)", gap: 14,
              flexShrink: 0, zIndex: 3, position: "relative",
            }}>
              <span style={{ fontFamily: "var(--font-display)", fontStyle: "italic", fontSize: 13, color: "var(--t-bronze)", letterSpacing: "0.04em" }}>
                topologia · locorum chartæ
              </span>
              <span style={{ flex: 1 }}/>
              <button onClick={() => setSection("all")} className="t-btn" style={{ padding: "4px 12px", fontSize: 11 }}>
                ← back <span className="key">g</span>
              </button>
            </div>
            <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
              <GraphView
                graphData={graphData}
                onOpen={handleOpenNode}
                focusUid={selectedUid}
              />
            </div>
          </div>
        )}

        {section === "graph" && !graphData && (
          <div style={{ flex: 1, display: "grid", placeItems: "center", background: "var(--t-bg)" }}>
            <span className="tel">loading topology…</span>
          </div>
        )}

        {section === "settings" && (
          <div style={{ flex: 1, display: "flex", flexDirection: "column" }} className="canvas">
            <div style={{
              padding: "14px 24px 12px", borderBottom: "1px solid var(--t-rule)",
              background: "rgba(6,9,20,0.65)", flexShrink: 0,
              display: "flex", alignItems: "center", gap: 14,
            }}>
              <span style={{ fontFamily: "var(--font-display)", fontWeight: 500, fontSize: 18, color: "var(--t-fg)" }}>Calibration</span>
              <span className="latin-twin">calibratio · vault health</span>
              <span style={{ flex: 1 }}/>
              <span className="tel">vault · <b>{allNodes.length}</b> loci</span>
            </div>
            <div style={{ flex: 1, display: "grid", placeItems: "center" }}>
              <div style={{ textAlign: "center" }}>
                <div className="smcaps" style={{ marginBottom: 14 }}>valetudo · health</div>
                <div style={{ fontFamily: "var(--font-display)", fontWeight: 500, fontSize: 72, color: "var(--t-fg)", lineHeight: 1 }}>
                  {allNodes.length}
                </div>
                <div className="tel" style={{ marginTop: 8 }}>loci in vault</div>
              </div>
            </div>
          </div>
        )}

        {/* Command palette overlay */}
        {cmdOpen && (
          <CommandPalette
            open={cmdOpen}
            onClose={() => setCmdOpen(false)}
            onOpen={handleOpenNode}
          />
        )}
        </div>
      </div>
    </div>
  );
}
