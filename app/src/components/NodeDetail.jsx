import { Fragment } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { TypeDot } from "./TypeDot.jsx";
import { Corners } from "./Corners.jsx";
import { Reticle } from "./Reticle.jsx";
import { Meridian } from "./Meridian.jsx";

const TYPE_COLOR = {
  project:"#2f6fc4", task:"#ff8a00", document:"#1fa050",
  entity:"#e63946", conversation:"#2dbfb6", article:"#f4c430",
  bookmark:"#c062b8", procedure:"#ff6b8a", topic:"#a4421f",
  event:"#7a5cc1", asset:"#5e7a8c", default:"#bab0ac",
};

const T_LATIN = {
  project: "negotium", task: "labor", document: "documentum",
  entity: "persona", conversation: "colloquium", article: "articulus",
  bookmark: "signum", procedure: "ratio", topic: "argumentum",
  event: "eventus", asset: "res", default: "ignotum",
};

export function NodeDetail({ node, neighbors, onOpenUid, onBack, onShowTopology, paper }) {
  if (!node) {
    return (
      <div style={{ flex: 1, display: "grid", placeItems: "center" }} className="canvas">
        <Meridian/>
        <div style={{ textAlign: "center", position: "relative", zIndex: 2 }}>
          <div className="smcaps" style={{ marginBottom: 14 }}>vacuum · empty</div>
          <p style={{ fontFamily: "var(--font-display)", fontStyle: "italic", fontSize: 18, color: "var(--t-fg-mute)" }}>
            Select a locus from the vault.
          </p>
        </div>
      </div>
    );
  }

  const outgoing = neighbors.filter(n => n.direction === "out");
  const incoming = neighbors.filter(n => n.direction === "in");
  const wordCount = (node.body || "").trim().split(/\s+/).filter(Boolean).length;

  return (
    <div className={`canvas ${paper ? "paper" : ""}`} style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
      <Meridian visible={!paper}/>
      <Reticle/>
      <Corners
        tl={{ label: "genus", value: node.type }}
        tr={{ label: "indicium", value: node.uid }}
        bl={{ label: "natum", value: (node.created_at || "").slice(0, 10) }}
        br={{ label: "renovatum", value: (node.updated_at || "").slice(0, 10) }}
      />

      {/* toolbar */}
      <div style={{
        padding: "14px 28px 12px", display: "flex", alignItems: "center", gap: 14,
        borderBottom: paper ? "1px solid var(--t-paper-3)" : "1px solid var(--t-rule)",
        background: paper ? "rgba(245,239,226,0.4)" : "rgba(6,9,20,0.65)",
        zIndex: 3, position: "relative", flexShrink: 0,
      }}>
        <button onClick={onBack} className="t-btn" style={{ padding: "4px 12px", fontSize: 11 }}>
          ← back <span className="key">esc</span>
        </button>
        <span className="tel">
          fol. · <b>{node.title?.slice(0, 32)}</b>
        </span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <span className="tel">{wordCount}w</span>
          <button onClick={onShowTopology} className="t-btn" style={{ padding: "4px 12px", fontSize: 11 }}>
            traverse <span className="key">g</span>
          </button>
        </div>
      </div>

      <div style={{ flex: 1, overflowY: "auto", display: "grid", gridTemplateColumns: "1fr 300px", gap: 32, padding: "40px 56px 56px" }}>
        <article style={{ maxWidth: 720, position: "relative" }}>
          {/* engraved overline */}
          <div style={{
            display: "flex", alignItems: "center", gap: 10, marginBottom: 14,
            fontFamily: "var(--font-display)", fontStyle: "italic", fontSize: 12,
            letterSpacing: "0.18em", textTransform: "lowercase",
            color: paper ? "var(--t-bronze-d)" : "var(--t-bronze)",
          }}>
            <TypeDot type={node.type} size={8}/>
            <span>{T_LATIN[node.type] || "ignotum"} · {node.type}</span>
            <span style={{ flex: 1, height: 0, borderTop: "0.5px solid currentColor", opacity: 0.5 }}/>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, fontStyle: "normal", letterSpacing: "0.04em" }}>
              {node.uid}
            </span>
          </div>

          <h1 style={{
            fontFamily: "var(--font-display)", fontWeight: 500, fontSize: 46, lineHeight: 1.08,
            letterSpacing: "-0.005em", margin: "0 0 24px",
            color: paper ? "var(--t-ink)" : "var(--t-fg)",
          }}>
            {node.title}
          </h1>

          {/* praefatio / frontmatter */}
          <div style={{
            marginBottom: 32,
            border: "0.5px solid var(--t-bronze-d)",
            outline: "0.5px solid var(--t-bronze-d)",
            outlineOffset: 3,
            padding: "14px 18px",
            background: paper ? "rgba(235,226,207,0.4)" : "rgba(10,16,32,0.5)",
          }}>
            <div style={{
              fontFamily: "var(--font-display)", fontStyle: "italic", fontSize: 11,
              color: paper ? "var(--t-bronze-d)" : "var(--t-bronze)",
              letterSpacing: "0.18em", textTransform: "lowercase",
              marginBottom: 10, display: "flex", justifyContent: "space-between",
            }}>
              <span>praefatio · frontmatter</span>
              <span style={{ fontFamily: "var(--font-mono)", fontStyle: "normal", fontSize: 9, letterSpacing: "0.04em", color: paper ? "#6b6960" : "var(--t-fg-faint)" }}>yaml</span>
            </div>
            <div style={{
              display: "grid", gridTemplateColumns: "120px 1fr", gap: "4px 16px",
              fontFamily: "var(--font-mono)", fontSize: 11.5,
              color: paper ? "var(--t-ink)" : "var(--t-fg)",
            }}>
              {[
                ["uid",     node.uid],
                ["type",    <span key="type"><TypeDot type={node.type} size={7}/> {node.type}</span>],
                ["status",  node.status || "—"],
                ["created", (node.created_at || "").slice(0, 10)],
                ["updated", (node.updated_at || "").slice(0, 10)],
                node.tags?.length   && ["tags",    node.tags.map(t => "#" + t).join(" ")],
                node.domains?.length && ["domains", node.domains.join(", ")],
              ].filter(Boolean).map(([k, v], i) => (
                <Fragment key={i}>
                  <span style={{ color: paper ? "#6b6960" : "var(--t-fg-mute)" }}>{k}</span>
                  <span style={{ display: "flex", gap: 6, alignItems: "center" }}>{v}</span>
                </Fragment>
              ))}
            </div>
          </div>

          {/* body */}
          <div style={{
            fontFamily: "var(--font-serif)", fontSize: paper ? 17 : 16,
            lineHeight: 1.65, letterSpacing: "0.005em",
            color: paper ? "var(--t-ink)" : "var(--t-fg)",
          }}>
            <div style={{
              fontFamily: "var(--font-display)", fontStyle: "italic", fontSize: 11,
              color: paper ? "var(--t-bronze-d)" : "var(--t-bronze)",
              letterSpacing: "0.18em", textTransform: "lowercase",
              marginBottom: 14,
            }}>corpus · body</div>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {node.body || ""}
            </ReactMarkdown>
          </div>

          {/* asset block */}
          {node.asset && (
            <div style={{
              marginTop: 32, padding: "14px 18px",
              border: "0.5px solid var(--t-bronze-d)",
              outline: "0.5px solid var(--t-bronze-d)", outlineOffset: 3,
              background: paper ? "rgba(235,226,207,0.4)" : "rgba(10,16,32,0.5)",
            }}>
              <div className="smcaps" style={{ marginBottom: 8 }}>res · asset</div>
              <div className="tel">{node.asset.mime_type} · {(node.asset.size_bytes / 1024).toFixed(1)} KB</div>
              <div className="tel" style={{ marginTop: 4, wordBreak: "break-all" }}>{node.asset.path}</div>
              {node.asset.content && (
                <pre style={{
                  marginTop: 12, padding: "10px 12px",
                  background: paper ? "rgba(235,226,207,0.6)" : "rgba(6,9,20,0.6)",
                  border: "0.5px solid var(--t-bronze-d)",
                  fontFamily: "var(--font-mono)", fontSize: 11, overflowX: "auto", whiteSpace: "pre-wrap",
                  color: paper ? "var(--t-ink)" : "var(--t-fg)",
                }}>
                  {node.asset.content.slice(0, 4000)}
                  {node.asset.content.length > 4000 ? "\n… truncated" : ""}
                </pre>
              )}
            </div>
          )}
        </article>

        {/* relations rail */}
        <aside style={{
          borderLeft: paper ? "1px solid var(--t-paper-3)" : "1px solid var(--t-rule)",
          paddingLeft: 24, position: "sticky", top: 0, alignSelf: "start",
        }}>
          <div style={{
            fontFamily: "var(--font-display)", fontStyle: "italic", fontSize: 12,
            color: paper ? "var(--t-bronze-d)" : "var(--t-bronze)",
            letterSpacing: "0.18em", textTransform: "lowercase",
            marginBottom: 14, display: "flex", justifyContent: "space-between", alignItems: "baseline",
          }}>
            <span>nexus · outbound</span>
            <span style={{ fontFamily: "var(--font-mono)", fontStyle: "normal", fontSize: 9, letterSpacing: "0.04em" }}>{outgoing.length}</span>
          </div>

          {/* mini topology */}
          {outgoing.length > 0 && (
            <div style={{ position: "relative", height: 160, marginBottom: 16 }}>
              <svg width="100%" height="100%" viewBox="-100 -80 200 160" style={{ overflow: "visible" }}>
                <circle cx="0" cy="0" r="20" fill={paper ? "rgba(122,90,46,0.08)" : "rgba(47,111,196,0.18)"}/>
                {outgoing.slice(0, 6).map((r, i, arr) => {
                  const a = (i / arr.length) * Math.PI * 2 - Math.PI / 2;
                  const x = Math.cos(a) * 65, y = Math.sin(a) * 55;
                  const color = TYPE_COLOR[r.type] || TYPE_COLOR.default;
                  return (
                    <g key={i}>
                      <line x1="0" y1="0" x2={x} y2={y}
                        stroke={color} strokeWidth="1"
                        className="edge-flow" opacity="0.85"/>
                      <circle cx={x} cy={y} r="4" fill={color}
                        stroke={paper ? "var(--t-paper)" : "var(--t-bg)"} strokeWidth="1"
                        style={{ cursor: "pointer" }}
                        onClick={() => onOpenUid(r.uid)}/>
                    </g>
                  );
                })}
                <circle cx="0" cy="0" r="5" fill={TYPE_COLOR[node.type] || TYPE_COLOR.default}
                  stroke={paper ? "var(--t-paper)" : "var(--t-bg)"} strokeWidth="1.5"/>
                <circle cx="0" cy="0" r="10" fill="none"
                  stroke={paper ? "var(--t-bronze-d)" : "var(--t-bronze)"} strokeWidth="0.5" opacity="0.7"/>
              </svg>
            </div>
          )}

          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {outgoing.map((r, i) => (
              <button key={i} onClick={() => onOpenUid(r.uid)} style={{
                display: "flex", gap: 8, alignItems: "flex-start", padding: "7px 0",
                border: 0, borderBottom: paper ? "0.5px dashed var(--t-paper-3)" : "0.5px dashed var(--t-rule)",
                background: "transparent", color: "inherit", textAlign: "left",
                cursor: "pointer", fontFamily: "var(--font-sans)", fontSize: 12,
              }}>
                <TypeDot type={r.type} size={7}/>
                <div style={{ flex: 1 }}>
                  <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: paper ? "var(--t-bronze-d)" : "var(--t-bronze)", letterSpacing: "0.06em", marginBottom: 2 }}>
                    — {r.rel_type} —
                  </div>
                  <div style={{ fontFamily: "var(--font-serif)", fontSize: 13, color: paper ? "var(--t-ink)" : "var(--t-fg)" }}>
                    {r.title}
                  </div>
                </div>
              </button>
            ))}
          </div>

          {incoming.length > 0 && (
            <>
              <div style={{
                fontFamily: "var(--font-display)", fontStyle: "italic", fontSize: 12,
                color: paper ? "var(--t-bronze-d)" : "var(--t-bronze)",
                letterSpacing: "0.18em", textTransform: "lowercase",
                margin: "20px 0 10px",
              }}>← nexus inbound</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 5, fontSize: 12 }}>
                {incoming.map((r, i) => (
                  <button key={i} onClick={() => onOpenUid(r.uid)} style={{
                    display: "flex", gap: 8, padding: "4px 0", alignItems: "center",
                    border: 0, background: "transparent", color: "inherit", textAlign: "left", cursor: "pointer",
                  }}>
                    <TypeDot type={r.type} size={7}/>
                    <span style={{ fontFamily: "var(--font-serif)", fontSize: 12, flex: 1, color: paper ? "var(--t-ink)" : "var(--t-fg)" }}>{r.title}</span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: paper ? "var(--t-bronze-d)" : "var(--t-bronze)" }}>{r.rel_type}</span>
                  </button>
                ))}
              </div>
            </>
          )}
        </aside>
      </div>
    </div>
  );
}
