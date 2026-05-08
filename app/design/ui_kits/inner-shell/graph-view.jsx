// GraphView — force-directed knowledge-graph visualisation.
// Aesthetic: Roman bronze tablet — engraved bezel ring with Latin
// inscription (antiquity) over a deep indigo void with glowing
// animated edges (futurism). Cardinal compass marks evoke the
// Roman cardo/decumanus axes used in surveying and forum layout.
//
// • Bezel ring (static, never rotates) carries the Latin type vocabulary
//   in italic small caps + Roman cardinal marks (N · E · S · W).
// • Inner field is --night void with a faint HUD grid + radial vignette.
// • Edges: 0.5px bronze hairlines for inert; 1.2px glowing colored beams
//   with animated dashed flow for the selected node's 1-hop neighbourhood.
// • Selected node: lapis halo + bronze outer ring + type-color inner ring
//   + viewfinder corner-bracket reticle.
// • Corner annotations in Latin: nodi · xiv (top-left), nexus · xxiii
//   (top-right), focus · loci · UID (bottom-left), via · I gradus (bottom-right).

const NIGHT = "#0a1020";
const NIGHT_2 = "#15203a";
const BRONZE = "#c9a86a";
const BRONZE_DARK = "#7a5a2e";
const PARCHMENT = "#f5efe2";
const FAINT = "#5a4520";
const RAIL_FG = "#d6cdb6";
const RAIL_MUTED = "#8896b8";

const LATIN_TYPES = "documentum · negotium · personae · colloquium · articulus · notatio · ratio · argumentum · res · eventus · topica";
const TO_ROMAN = (n) => {
  const m = [["m",1000],["cm",900],["d",500],["cd",400],["c",100],["xc",90],["l",50],["xl",40],["x",10],["ix",9],["v",5],["iv",4],["i",1]];
  let s = ""; for (const [r,v] of m) while (n >= v) { s += r; n -= v; } return s || "·";
};

const GraphView = ({ vault, onOpen, focusUid }) => {
  const W = 1200, H = 720;
  const CX = W / 2, CY = H / 2;
  const RING_R = 320;
  const svgRef = React.useRef(null);
  const [nodes, setNodes] = React.useState(null);
  const [selected, setSelected] = React.useState(focusUid || null);
  const [hoverUid, setHoverUid] = React.useState(null);
  const [hoverEdge, setHoverEdge] = React.useState(null);
  const [running, setRunning] = React.useState(true);
  const [relFilter, setRelFilter] = React.useState(new Set());
  const dragRef = React.useRef(null);

  React.useEffect(() => {
    const onKey = (e) => {
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
      if (e.key === " ") { e.preventDefault(); setRunning(r => !r); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // ─── derive edges (canonical pair, unique) ──────────────────────
  const edges = React.useMemo(() => {
    const seen = new Set();
    const out = [];
    vault.forEach(n => (n.relations || []).forEach(r => {
      const a = n.uid, b = r.uid;
      const key = [a, b].sort().join("|");
      if (seen.has(key)) return;
      seen.add(key);
      if (vault.find(x => x.uid === b)) out.push({ source: a, target: b, type: r.type });
    }));
    return out;
  }, [vault]);

  const relationTypes = React.useMemo(() => [...new Set(edges.map(e => e.type))].sort(), [edges]);

  // ─── init nodes on a soft inner ring ───────────────────────────
  React.useEffect(() => {
    let s = 1;
    const rand = () => { s = (s * 9301 + 49297) % 233280; return s / 233280; };
    const init = vault.map((n, i) => {
      const a = (i / vault.length) * Math.PI * 2;
      const r = 180 + rand() * 60;
      return { ...n, x: CX + Math.cos(a) * r, y: CY + Math.sin(a) * r, vx: 0, vy: 0, fixed: false };
    });
    setNodes(init);
  }, [vault]);

  // ─── force simulation ──────────────────────────────────────────
  React.useEffect(() => {
    if (!nodes || !running) return;
    let raf;
    const step = () => {
      setNodes(prev => {
        if (!prev) return prev;
        const next = prev.map(n => ({ ...n }));
        const byUid = Object.fromEntries(next.map(n => [n.uid, n]));
        for (let i = 0; i < next.length; i++) {
          for (let j = i + 1; j < next.length; j++) {
            const a = next[i], b = next[j];
            let dx = a.x - b.x, dy = a.y - b.y;
            let d2 = dx * dx + dy * dy + 0.01;
            const force = 5400 / d2;
            const d = Math.sqrt(d2);
            const fx = (dx / d) * force, fy = (dy / d) * force;
            a.vx += fx; a.vy += fy;
            b.vx -= fx; b.vy -= fy;
          }
        }
        edges.forEach(e => {
          const a = byUid[e.source], b = byUid[e.target];
          if (!a || !b) return;
          const dx = b.x - a.x, dy = b.y - a.y;
          const d = Math.sqrt(dx * dx + dy * dy) + 0.01;
          const f = (d - 130) * 0.018;
          const fx = (dx / d) * f, fy = (dy / d) * f;
          a.vx += fx; a.vy += fy;
          b.vx -= fx; b.vy -= fy;
        });
        next.forEach(n => {
          n.vx += (CX - n.x) * 0.005;
          n.vy += (CY - n.y) * 0.005;
        });
        next.forEach(n => {
          if (n.fixed) { n.vx = 0; n.vy = 0; return; }
          n.vx *= 0.78; n.vy *= 0.78;
          n.x += n.vx; n.y += n.vy;
          // soft inner-ring containment
          const dx = n.x - CX, dy = n.y - CY;
          const d = Math.sqrt(dx * dx + dy * dy);
          if (d > RING_R - 30) {
            const k = (RING_R - 30) / d;
            n.x = CX + dx * k; n.y = CY + dy * k;
          }
        });
        return next;
      });
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [nodes !== null, edges, running]);

  if (!nodes) return null;
  const byUid = Object.fromEntries(nodes.map(n => [n.uid, n]));

  const neighbours = new Set();
  if (selected) {
    neighbours.add(selected);
    edges.forEach(e => {
      if (e.source === selected) neighbours.add(e.target);
      if (e.target === selected) neighbours.add(e.source);
    });
  }
  const visibleEdges = edges.filter(e => relFilter.size === 0 || relFilter.has(e.type));

  // svg coordinate helper
  const screenToSvg = (clientX, clientY) => {
    const r = svgRef.current.getBoundingClientRect();
    return {
      x: (clientX - r.left) * (W / r.width),
      y: (clientY - r.top) * (H / r.height)
    };
  };
  const onPointerDown = (uid) => (e) => {
    e.stopPropagation();
    const p = screenToSvg(e.clientX, e.clientY);
    dragRef.current = { uid, dx: p.x - byUid[uid].x, dy: p.y - byUid[uid].y };
    setNodes(prev => prev.map(n => n.uid === uid ? { ...n, fixed: true } : n));
  };
  const onPointerMove = (e) => {
    if (!dragRef.current) return;
    const p = screenToSvg(e.clientX, e.clientY);
    const { uid, dx, dy } = dragRef.current;
    setNodes(prev => prev.map(n => n.uid === uid ? { ...n, x: p.x - dx, y: p.y - dy, vx: 0, vy: 0 } : n));
  };
  const onPointerUp = () => { dragRef.current = null; };

  const counts = {};
  TYPES.forEach(([t]) => counts[t] = nodes.filter(n => n.type === t).length);

  // ─── render ────────────────────────────────────────────────────
  return (
    <div style={{ display: "flex", flex: 1, minHeight: 0, minWidth: 0, background: NIGHT, color: PARCHMENT, fontFamily: "var(--font-sans)" }}>
      {/* css for edge flow animation */}
      <style>{`@keyframes loci-flow { to { stroke-dashoffset: -16; } } .loci-edge-active { animation: loci-flow 3s linear infinite; }`}</style>

      {/* canvas */}
      <div style={{ flex: 1, position: "relative", overflow: "hidden", minWidth: 0,
        background: `radial-gradient(ellipse at center, ${NIGHT_2} 0%, ${NIGHT} 75%)`
      }}>
        {/* HUD grid backdrop */}
        <div style={{
          position: "absolute", inset: 0,
          backgroundImage: `linear-gradient(to right, rgba(245,239,226,0.025) 1px, transparent 1px), linear-gradient(to bottom, rgba(245,239,226,0.025) 1px, transparent 1px)`,
          backgroundSize: "32px 32px", pointerEvents: "none"
        }}/>

        {/* corner annotations */}
        <Corner pos="tl"><i>nodi</i><b>{TO_ROMAN(nodes.length)}</b></Corner>
        <Corner pos="tr"><i>nexus</i><b>{TO_ROMAN(visibleEdges.length)}</b></Corner>
        <Corner pos="bl">
          {selected ? <><i>focus · loci</i><b>{selected}</b></> : <><i>focus</i><b>—</b></>}
        </Corner>
        <Corner pos="br">
          {selected ? <><i>via</i><b>{TO_ROMAN(neighbours.size - 1)} · gradus</b></> : <><i>via</i><b>—</b></>}
        </Corner>

        {/* topbar — heading + controls */}
        <div style={{ position: "absolute", top: 0, left: 0, right: 0, padding: "16px 22px 28px", display: "flex", alignItems: "center", gap: 14, zIndex: 4, pointerEvents: "none", background: `linear-gradient(to bottom, ${NIGHT} 50%, transparent)` }}>
          <h1 style={{ fontFamily: "var(--font-display)", fontWeight: 500, fontSize: 22, margin: 0, color: PARCHMENT, whiteSpace: "nowrap", letterSpacing: "0.01em" }}>Topology</h1>
          <span style={{ fontFamily: "var(--font-display)", fontStyle: "italic", fontSize: 13, color: BRONZE, letterSpacing: "0.04em", whiteSpace: "nowrap" }}>— locorum chartæ —</span>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: RAIL_MUTED, whiteSpace: "nowrap", marginLeft: "auto" }}>
            {nodes.length} nodes · {visibleEdges.length} edges{selected ? ` · ${neighbours.size - 1}-hop` : ""}
          </span>
          <div style={{ display: "flex", gap: 6, pointerEvents: "auto", flexShrink: 0 }}>
            <GButton onClick={() => setRunning(r => !r)}>{running ? "⏸ pause" : "▶ resume"}</GButton>
            <GButton onClick={() => { setSelected(null); setRelFilter(new Set()); }}>reset</GButton>
          </div>
        </div>

        <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet"
             onPointerMove={onPointerMove} onPointerUp={onPointerUp}
             onClick={() => setSelected(null)}
             style={{ width: "100%", height: "100%", display: "block", cursor: dragRef.current ? "grabbing" : "default" }}>
          <defs>
            <filter id="loci-glow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="2.4" result="b"/>
              <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
            </filter>
            {TYPES.map(([t, c]) => (
              <radialGradient key={"halo-"+t} id={`halo-${t}`} cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor={c} stopOpacity="0.55"/>
                <stop offset="100%" stopColor={c} stopOpacity="0"/>
              </radialGradient>
            ))}
            {TYPES.map(([t, c]) => (
              <marker key={"ar-"+t} id={`loci-ar-${t}`} viewBox="0 -4 8 8" refX="8" refY="0" markerWidth="6" markerHeight="6" orient="auto">
                <path d="M0,-4L8,0L0,4" fill={c} opacity="0.85"/>
              </marker>
            ))}
            <path id="loci-bezel-top" d={`M ${CX - RING_R - 6},${CY} A ${RING_R + 6},${RING_R + 6} 0 0,1 ${CX + RING_R + 6},${CY}`} fill="none"/>
            <path id="loci-bezel-bot" d={`M ${CX + RING_R + 6},${CY} A ${RING_R + 6},${RING_R + 6} 0 0,1 ${CX - RING_R - 6},${CY}`} fill="none"/>
          </defs>

          {/* bezel: bronze rings + Latin engraving + cardinals + ticks */}
          <g>
            <circle cx={CX} cy={CY} r={RING_R} fill="none" stroke={BRONZE_DARK} strokeWidth="0.7" opacity="0.7"/>
            <circle cx={CX} cy={CY} r={RING_R - 5} fill="none" stroke={BRONZE_DARK} strokeWidth="0.4" opacity="0.5"/>
            <text fontFamily="var(--font-display)" fontStyle="italic" fontSize="11" fill={BRONZE} letterSpacing="0.18em" style={{textTransform:"lowercase"}}>
              <textPath href="#loci-bezel-top" startOffset="50%" textAnchor="middle">{LATIN_TYPES}</textPath>
            </text>
            <text fontFamily="var(--font-display)" fontStyle="italic" fontSize="11" fill={BRONZE} letterSpacing="0.18em" style={{textTransform:"lowercase"}}>
              <textPath href="#loci-bezel-bot" startOffset="50%" textAnchor="middle">memoria · vinculum · indicium · radix · semita · gradus · meminisse</textPath>
            </text>
            {/* cardinal compass marks */}
            <g fontFamily="var(--font-display)" fontSize="13" fill={BRONZE} fontWeight="500">
              <text x={CX} y={CY - RING_R - 16} textAnchor="middle">N</text>
              <text x={CX + RING_R + 16} y={CY + 4}>E</text>
              <text x={CX} y={CY + RING_R + 22} textAnchor="middle">S</text>
              <text x={CX - RING_R - 16} y={CY + 4} textAnchor="end">W</text>
            </g>
            {/* HUD meridians */}
            <line x1={CX} y1={CY - RING_R} x2={CX} y2={CY + RING_R} stroke={BRONZE} strokeWidth="0.4" strokeDasharray="1 5" opacity="0.4"/>
            <line x1={CX - RING_R} y1={CY} x2={CX + RING_R} y2={CY} stroke={BRONZE} strokeWidth="0.4" strokeDasharray="1 5" opacity="0.4"/>
            {/* 30° tick marks */}
            {[...Array(12)].map((_, i) => {
              const a = (i / 12) * Math.PI * 2 - Math.PI / 2;
              const x1 = CX + Math.cos(a) * RING_R, y1 = CY + Math.sin(a) * RING_R;
              const x2 = CX + Math.cos(a) * (RING_R - 8), y2 = CY + Math.sin(a) * (RING_R - 8);
              return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke={BRONZE_DARK} strokeWidth="0.6"/>;
            })}
          </g>

          {/* edges */}
          {visibleEdges.map((e, i) => {
            const a = byUid[e.source], b = byUid[e.target];
            if (!a || !b) return null;
            const adjacent = !selected || (e.source === selected || e.target === selected);
            const dim = selected && !(e.source === selected || e.target === selected);
            const c = TYPE_COLOR[a.type] || BRONZE;
            return (
              <g key={i} opacity={dim ? 0.18 : 1}
                 onMouseEnter={() => setHoverEdge(i)} onMouseLeave={() => setHoverEdge(null)}>
                {adjacent && selected ? (
                  <line x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                        stroke={c} strokeWidth="1.4" strokeDasharray="3 4"
                        opacity="0.85" filter="url(#loci-glow)"
                        markerEnd={`url(#loci-ar-${a.type})`}
                        className="loci-edge-active"/>
                ) : (
                  <line x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                        stroke={FAINT} strokeWidth="0.6" opacity="0.7"/>
                )}
                {(hoverEdge === i || (selected && (e.source === selected || e.target === selected))) && (
                  <g pointerEvents="none">
                    <rect x={(a.x + b.x) / 2 - e.type.length * 3.5} y={(a.y + b.y) / 2 - 9}
                          width={e.type.length * 7} height={15} rx={2}
                          fill={NIGHT_2} stroke={BRONZE} strokeWidth="0.4"/>
                    <text x={(a.x + b.x) / 2} y={(a.y + b.y) / 2 + 2} textAnchor="middle"
                          fontFamily="var(--font-mono)" fontSize="10" fill={BRONZE}
                          letterSpacing="0.04em">{e.type}</text>
                  </g>
                )}
              </g>
            );
          })}

          {/* nodes */}
          {nodes.map(n => {
            const isSel = selected === n.uid;
            const isHov = hoverUid === n.uid;
            const isNbr = !selected || neighbours.has(n.uid);
            const c = TYPE_COLOR[n.type] || "#bab0ac";
            return (
              <g key={n.uid}
                 transform={`translate(${n.x},${n.y})`}
                 opacity={isNbr ? 1 : 0.22}
                 style={{ cursor: "grab" }}
                 onPointerDown={onPointerDown(n.uid)}
                 onMouseEnter={() => setHoverUid(n.uid)} onMouseLeave={() => setHoverUid(null)}
                 onClick={(e) => { e.stopPropagation(); setSelected(n.uid); }}
                 onDoubleClick={(e) => { e.stopPropagation(); onOpen && onOpen(n.uid); }}>
                {/* halo */}
                {(isSel || isHov || isNbr && selected) && (
                  <circle r={isSel ? 26 : 14} fill={`url(#halo-${n.type})`} opacity={isSel ? 1 : 0.6}/>
                )}
                {/* selected: bronze outer ring */}
                {isSel && <circle r="14" fill="none" stroke={BRONZE} strokeWidth="0.8"/>}
                {/* type-color inner ring on selected */}
                {isSel && <circle r="9.5" fill="none" stroke={c} strokeWidth="1.2" opacity="0.85"/>}
                {/* pinned indicator */}
                {n.fixed && !isSel && <circle r="9" fill="none" stroke={c} strokeWidth="0.6" strokeDasharray="2 2"/>}
                {/* core */}
                <circle r={isSel ? 5.5 : 4.5} fill={c} stroke={NIGHT} strokeWidth="1"/>
                {/* viewfinder reticle on selected */}
                {isSel && (
                  <g stroke={BRONZE} strokeWidth="0.7" fill="none" opacity="0.85">
                    <path d="M -22,-16 L -22,-22 L -16,-22"/>
                    <path d="M  22,-16 L  22,-22 L  16,-22"/>
                    <path d="M -22, 16 L -22, 22 L -16, 22"/>
                    <path d="M  22, 16 L  22, 22 L  16, 22"/>
                  </g>
                )}
                {/* labels */}
                <text y={(isSel ? 36 : 18)} textAnchor="middle"
                      fontFamily="var(--font-mono)" fontSize="10"
                      fontWeight={isSel ? 600 : 400}
                      letterSpacing="0.04em"
                      fill={isSel ? PARCHMENT : RAIL_FG}
                      style={{textTransform: isSel ? "uppercase" : "lowercase"}}>
                  {n.title.length > 24 ? n.title.slice(0, 24) + "…" : n.title}
                </text>
                <text y={(isSel ? 48 : 30)} textAnchor="middle"
                      fontFamily="var(--font-mono)" fontSize="8"
                      fill={isSel ? BRONZE : RAIL_MUTED}>
                  {n.uid}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* right rail — dark-mode legend / filter / inspector */}
      <aside style={{ width: 280, flexShrink: 0, borderLeft: `1px solid ${BRONZE_DARK}33`, background: NIGHT, display: "flex", flexDirection: "column", overflowY: "auto", color: PARCHMENT }}>
        <DSection title="Types · Genera">
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "5px 12px" }}>
            {TYPES.filter(([t]) => counts[t] > 0).map(([t]) => (
              <div key={t} style={{ display: "flex", alignItems: "center", gap: 6, fontFamily: "var(--font-mono)", fontSize: 10, color: RAIL_FG, letterSpacing: "0.03em" }}>
                <TypeDot type={t} size={8}/>
                <span style={{ flex: 1, textTransform: "lowercase" }}>{t}</span>
                <span style={{ color: BRONZE }}>{TO_ROMAN(counts[t])}</span>
              </div>
            ))}
          </div>
        </DSection>

        <DSection title="Relations · Vincula" subtitle={relFilter.size ? `${relFilter.size} active` : "click to isolate"}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
            {relationTypes.map(rt => {
              const on = relFilter.has(rt);
              return (
                <button key={rt} onClick={() => {
                  setRelFilter(prev => {
                    const next = new Set(prev);
                    on ? next.delete(rt) : next.add(rt);
                    return next;
                  });
                }} style={{
                  fontFamily: "var(--font-mono)", fontSize: 10, padding: "3px 8px",
                  background: on ? BRONZE : "transparent",
                  color: on ? NIGHT : BRONZE,
                  border: `1px solid ${on ? BRONZE : BRONZE_DARK}`,
                  borderRadius: 2, cursor: "pointer", whiteSpace: "nowrap", letterSpacing: "0.03em"
                }}>{rt}</button>
              );
            })}
          </div>
        </DSection>

        <DSection title="Focus · Inspector">
          {selected ? (() => {
            const n = byUid[selected];
            const inc = edges.filter(e => e.target === selected).length;
            const out = edges.filter(e => e.source === selected).length;
            return (
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
                  <TypeDot type={n.type}/>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: RAIL_MUTED }}>{n.type} · {n.uid}</span>
                </div>
                <div style={{ fontFamily: "var(--font-display)", fontSize: 18, lineHeight: 1.25, color: PARCHMENT, marginBottom: 10 }}>{n.title}</div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginBottom: 12 }}>
                  <DStat label="degree" value={TO_ROMAN(inc + out)}/>
                  <DStat label="out · in" value={`${TO_ROMAN(out) || "·"} · ${TO_ROMAN(inc) || "·"}`}/>
                </div>
                <button onClick={() => onOpen && onOpen(n.uid)} style={{
                  width: "100%", padding: "8px 10px", fontFamily: "var(--font-sans)", fontSize: 12,
                  background: BRONZE, color: NIGHT, border: 0, borderRadius: 3, cursor: "pointer", letterSpacing: "0.04em"
                }}>open node →</button>
              </div>
            );
          })() : (
            <div style={{ fontFamily: "var(--font-display)", fontStyle: "italic", fontSize: 13, color: RAIL_MUTED, lineHeight: 1.5 }}>
              Click a locus to isolate its first-degree neighbourhood. Drag to fix in place. Double-click to open.
            </div>
          )}
        </DSection>

        <div style={{ marginTop: "auto", padding: "12px 14px", borderTop: `1px solid ${BRONZE_DARK}33`, fontFamily: "var(--font-mono)", fontSize: 9, color: RAIL_MUTED, display: "flex", flexDirection: "column", gap: 3, letterSpacing: "0.04em" }}>
          <span>drag · pin · dblclick · open</span>
          <span>space · pause · esc · close</span>
        </div>
      </aside>
    </div>
  );
};

// ─── helpers ─────────────────────────────────────────────────────
const Corner = ({ pos, children }) => {
  const styles = {
    tl: { top: 56, left: 22, textAlign: "left" },
    tr: { top: 56, right: 22, textAlign: "right" },
    bl: { bottom: 14, left: 22, textAlign: "left" },
    br: { bottom: 14, right: 22, textAlign: "right" },
  };
  return (
    <div style={{
      position: "absolute", zIndex: 2, pointerEvents: "none",
      fontFamily: "var(--font-mono)", fontSize: 9, color: BRONZE,
      letterSpacing: "0.08em", textTransform: "lowercase",
      lineHeight: 1.4,
      ...styles[pos]
    }}>
      {React.Children.map(children, child => {
        if (!child) return null;
        if (child.type === "i") return <div style={{ color: RAIL_MUTED, fontStyle: "normal" }}>{child.props.children}</div>;
        if (child.type === "b") return <div style={{ color: PARCHMENT, fontWeight: 400 }}>{child.props.children}</div>;
        return child;
      })}
    </div>
  );
};

const DSection = ({ title, subtitle, children }) => (
  <div style={{ padding: "14px 16px", borderBottom: `1px solid ${BRONZE_DARK}33` }}>
    <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 10 }}>
      <span style={{ fontFamily: "var(--font-display)", fontStyle: "italic", fontSize: 11, fontWeight: 500, letterSpacing: "0.06em", color: BRONZE }}>{title}</span>
      {subtitle && <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: RAIL_MUTED }}>{subtitle}</span>}
    </div>
    {children}
  </div>
);

const DStat = ({ label, value }) => (
  <div style={{ background: NIGHT_2, padding: "6px 8px", borderRadius: 2, border: `1px solid ${BRONZE_DARK}55` }}>
    <div style={{ fontFamily: "var(--font-display)", fontStyle: "italic", fontSize: 9, color: RAIL_MUTED, letterSpacing: "0.06em" }}>{label}</div>
    <div style={{ fontFamily: "var(--font-display)", fontSize: 16, color: BRONZE, marginTop: 2, letterSpacing: "0.04em" }}>{value}</div>
  </div>
);

const GButton = ({ children, onClick, title }) => (
  <button onClick={onClick} title={title} style={{
    fontFamily: "var(--font-mono)", fontSize: 11, padding: "5px 12px",
    background: "rgba(10,16,32,0.7)", backdropFilter: "blur(6px)",
    border: `1px solid ${BRONZE_DARK}`, borderRadius: 3,
    color: BRONZE, cursor: "pointer", whiteSpace: "nowrap", letterSpacing: "0.04em"
  }}>{children}</button>
);

window.GraphView = GraphView;
