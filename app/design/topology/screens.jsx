// Screens for the topology-vibe prototype.
// All assume VAULT, TYPE_COLOR-style atoms are loaded.

const TYPE_COLOR = {
  project:"#2f6fc4", task:"#ff8a00", document:"#1fa050",
  entity:"#e63946", conversation:"#2dbfb6", article:"#f4c430",
  bookmark:"#c062b8", procedure:"#ff6b8a", topic:"#a4421f",
  event:"#7a5cc1", asset:"#5e7a8c", default:"#bab0ac"
};

// ─────────────────────────────────────────────────────────
// Splash — observatory entry plate
// ─────────────────────────────────────────────────────────
function SplashScreen({ onEnter, motion }) {
  return (
    <div className="canvas">
      <Meridian/>
      <Reticle/>
      <Corners
        tl={{label:'thesaurus', value:'~/Nextcloud/loci'}}
        tr={{label:'caelum', value:'observatorium · v0.4'}}
        bl={{label:'fundatum', value:'mmxxvi · iv'}}
        br={{label:'lat ·  long', value:'40.7128 · -74.0060'}}
      />

      {/* central bezel with monogram */}
      <div style={{
        position:'absolute', left:'50%', top:'50%',
        transform:'translate(-50%, -50%)',
        zIndex:2, pointerEvents:'none'
      }}>
        <Bezel size={420} rotate={motion === 'ambient'}
          items={["documentum","negotium","persona","colloquium","articulus","signum","ratio","argumentum","eventus","res"]}/>
      </div>

      <div className="splash">
        <div className="splash-stack">
          <div className="super">memoriae thesaurus</div>
          <h1 className="h-display">
            Save your thinking<br/>as <em>loci</em>.
          </h1>
          <p className="lead">
            A vault of plain Markdown, organised as a traversable graph.
            Walk the route. Find your way back.
          </p>
          <div className="splash-actions">
            <button className="t-btn solid" onClick={onEnter}>
              enter the vault <span className="key">⏎</span>
            </button>
            <button className="t-btn">
              configure <span className="key">⌘,</span>
            </button>
          </div>
        </div>
      </div>

      {/* engraved footer Latin */}
      <div style={{
        position:'absolute', left:0, right:0, bottom:46, textAlign:'center',
        fontFamily:'var(--serif)', fontStyle:'italic', fontSize:11,
        color:'var(--t-bronze-d)', letterSpacing:'0.34em', textTransform:'lowercase',
        zIndex:3
      }}>
        ❦ &nbsp; loca · &nbsp; nexus · &nbsp; ratio &nbsp; ❦
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────
// Vault rail (sidebar)
// ─────────────────────────────────────────────────────────
function VaultRail({ active, onNav, vault, density }) {
  const types = ["project","task","document","entity","conversation","article","bookmark","procedure","topic","event","asset"];
  const counts = {};
  types.forEach(t => counts[t] = vault.filter(n => n.type === t).length);

  const Row = ({ id, type, label, count, latin, icon }) => (
    <button
      className={`rail-row ${active === id ? 'active' : ''}`}
      onClick={() => onNav(id)}
    >
      {type
        ? <TypeDot type={type} size={8}/>
        : <span style={{
            width: 14, height: 14, display:'inline-flex', alignItems:'center',
            justifyContent:'center', color:'var(--t-bronze)'
          }}>{icon}</span>}
      <span style={{flex:1, display:'flex', flexDirection:'column', lineHeight:1.05}}>
        <span>{label}</span>
        {latin && <span style={{
          fontFamily:'var(--serif)', fontStyle:'italic', fontSize:9.5,
          color:'var(--t-fg-faint)', letterSpacing:'0.06em'
        }}>{latin}</span>}
      </span>
      {count != null && <span className="count">{count.toString().padStart(3,'0')}</span>}
    </button>
  );

  return (
    <aside className="rail">
      <div className="rail-head">
        <span className="wm">Loci</span>
        <span className="ver">v0.4 · mmxxvi</span>
      </div>

      <div style={{padding:'8px 0', display:'flex', flexDirection:'column', gap:0, overflowY:'auto'}}>
        <div className="rail-section">prima · primary <span className="roman">I</span></div>
        <Row id="splash" label="Splash"   latin="ianua"      icon="⌂"/>
        <Row id="all"    label="All loci" latin="omnia loca" icon="∎" count={vault.length}/>
        <Row id="recent" label="Recent"   latin="recentia"   icon="↺" count={6}/>
        <Row id="graph"  label="Topology" latin="topologia"  icon="◌"/>
        <Row id="empty"  label="Inbox"    latin="ingressus"  icon="□" count={0}/>

        <div className="rail-section">genera · types <span className="roman">II</span></div>
        {types.map(t => (
          <Row key={t} id={`t:${t}`} type={t} label={t} latin={T_LATIN[t]} count={counts[t]}/>
        ))}

        <div className="rail-section">instrumenta · tools <span className="roman">III</span></div>
        <Row id="compose"  label="Compose"  latin="componere"   icon="✎"/>
        <Row id="cmd"      label="Command"  latin="praeceptum"  icon="⌘"/>
        <Row id="settings" label="Settings" latin="calibratio"  icon="⚙"/>
      </div>

      <div className="rail-foot">
        <div className="health">vault healthy · 17 loci · 23 nexus</div>
        <div style={{color:'var(--t-fg-faint)', fontSize:9}}>~/Nextcloud/loci</div>
      </div>
    </aside>
  );
}

// ─────────────────────────────────────────────────────────
// Vault index (list of nodes)
// ─────────────────────────────────────────────────────────
function VaultIndex({ vault, selectedUid, onOpen }) {
  return (
    <div style={{flex:1, display:'flex', flexDirection:'column', position:'relative', minWidth:0}} className="canvas">
      <Meridian visible={false}/>

      <HeaderStrip
        label="All loci"
        latin="omnia loca · folio I"
        telemetry={<><b>17</b> nodes · <b>23</b> nexus · sorted by <b>updated</b> ↓</>}
        right={
          <div style={{display:'flex', gap:8, alignItems:'center'}}>
            <span className="tel">⌘K</span>
            <button className="t-btn" style={{padding:'5px 12px', fontSize:12}}>
              new locus <span className="key">⌘N</span>
            </button>
          </div>
        }
      />

      <div style={{padding:'8px 24px', display:'flex', alignItems:'center', gap:14, borderBottom:'1px solid var(--t-rule-soft)'}}>
        <span className="smcaps">filter</span>
        {["all","project","topic","article","bookmark","conversation","procedure","entity","task","document"].slice(0,7).map((t,i) => (
          <span key={t} className="t-chip" style={{cursor:'pointer', opacity: i===0 ? 1 : 0.6}}>
            {t !== 'all' && <TypeDot type={t} size={6}/>}
            {t}
          </span>
        ))}
        <span style={{marginLeft:'auto'}} className="tel">page <b>i</b> of <b>iii</b></span>
      </div>

      {/* column headers */}
      <div style={{
        display:'grid',
        gridTemplateColumns:'18px 1fr 90px 110px 80px',
        gap:14, padding:'8px 24px',
        borderBottom:'1px solid var(--t-rule)',
        fontFamily:'var(--mono)', fontSize:9.5, color:'var(--t-bronze)',
        letterSpacing:'0.12em', textTransform:'uppercase'
      }}>
        <span/>
        <span>title <span style={{fontFamily:'var(--serif)',fontStyle:'italic',color:'var(--t-bronze-d)',letterSpacing:'0.04em',textTransform:'lowercase'}}>· titulus</span></span>
        <span>type <span style={{fontFamily:'var(--serif)',fontStyle:'italic',color:'var(--t-bronze-d)',letterSpacing:'0.04em',textTransform:'lowercase'}}>· genus</span></span>
        <span>uid</span>
        <span>updated</span>
      </div>

      <div style={{flex:1, overflowY:'auto'}}>
        {vault.map(n => (
          <div
            key={n.uid}
            className={`list-row ${selectedUid === n.uid ? 'selected' : ''}`}
            onClick={() => onOpen(n.uid)}
          >
            <TypeDot type={n.type}/>
            <div>
              <div className="lr-title">{n.title}</div>
              {n.tags && n.tags.length > 0 && (
                <div style={{marginTop:3, display:'flex', gap:6}}>
                  {n.tags.slice(0,3).map(t => (
                    <span key={t} style={{
                      fontFamily:'var(--mono)', fontSize:9,
                      color:'var(--t-fg-faint)', letterSpacing:'0.04em'
                    }}>#{t}</span>
                  ))}
                </div>
              )}
            </div>
            <span className="lr-type">{n.type}</span>
            <span className="lr-uid">{n.uid}</span>
            <span className="lr-date">{n.updated}</span>
          </div>
        ))}
      </div>

      <Corners
        bl={{label:'focus · selectum', value: selectedUid || '—'}}
        br={{label:'gradus · zoom', value:'i · 100%'}}
      />
    </div>
  );
}

// ─────────────────────────────────────────────────────────
// Node detail — paper / engraved page
// ─────────────────────────────────────────────────────────
function NodeDetail({ node, vault, onOpen, onBack, paper }) {
  if (!node) return null;
  const related = (node.relations || []).map(r => ({...r, target: vault.find(n => n.uid === r.uid)})).filter(r => r.target);
  const inbound = vault.filter(n => (n.relations||[]).some(r => r.uid === node.uid))
    .map(n => ({ from: n, type: n.relations.find(r => r.uid === node.uid)?.type }));

  return (
    <div className={`canvas ${paper ? 'paper' : ''}`} style={{display:'flex', flexDirection:'column'}}>
      <Meridian visible={!paper}/>
      <Reticle/>

      <Corners
        tl={{label:'genus', value: node.type}}
        tr={{label:'indicium', value: node.uid}}
        bl={{label:'natum', value: node.created}}
        br={{label:'renovatum', value: node.updated}}
      />

      <div style={{
        padding:'18px 28px 12px',
        display:'flex', alignItems:'center', gap:14,
        borderBottom: paper ? '1px solid var(--t-paper-3)' : '1px solid var(--t-rule)',
        background: paper ? 'rgba(245,239,226,0.4)' : 'rgba(6,9,20,0.65)',
        zIndex: 3, position:'relative'
      }}>
        <button onClick={onBack} className="t-btn" style={{padding:'4px 12px', fontSize:11}}>
          ← back <span className="key">esc</span>
        </button>
        <span className="tel" style={{color: paper ? 'var(--t-bronze-d)' : undefined}}>
          fol. <b>iii</b> · folio of <b>{node.title.slice(0,32)}</b>
        </span>
        <div style={{marginLeft:'auto', display:'flex', gap:8}}>
          <button className="t-btn" style={{padding:'4px 12px', fontSize:11}}>edit <span className="key">e</span></button>
          <button className="t-btn" style={{padding:'4px 12px', fontSize:11}}>traverse <span className="key">g</span></button>
        </div>
      </div>

      <div style={{flex:1, overflowY:'auto', display:'grid', gridTemplateColumns:'1fr 320px', gap:32, padding:'40px 56px 56px', maxWidth:'100%'}}>
        <article style={{maxWidth:720, position:'relative'}}>
          {/* engraved overline */}
          <div style={{
            display:'flex', alignItems:'center', gap:10, marginBottom:14,
            fontFamily:'var(--serif)', fontStyle:'italic', fontSize:12,
            letterSpacing:'0.18em', textTransform:'lowercase',
            color: paper ? 'var(--t-bronze-d)' : 'var(--t-bronze)'
          }}>
            <TypeDot type={node.type} size={8}/>
            <span>{T_LATIN[node.type]} · {node.type}</span>
            <span style={{
              flex:1, height:0, borderTop:'0.5px solid currentColor', opacity:0.5
            }}/>
            <span style={{fontFamily:'var(--mono)', fontSize:10, fontStyle:'normal', letterSpacing:'0.04em'}}>
              {node.uid}
            </span>
          </div>

          <h1 style={{
            fontFamily:'var(--serif)', fontWeight:500, fontSize:46, lineHeight:1.08,
            letterSpacing:'-0.005em', margin:'0 0 24px',
            color: paper ? 'var(--t-ink)' : 'var(--t-fg)'
          }}>
            {node.title}
          </h1>

          {/* praefatio / frontmatter */}
          <div style={{
            marginBottom:32,
            border: paper ? '0.5px solid var(--t-bronze-d)' : '0.5px solid var(--t-bronze-d)',
            outline: '0.5px solid currentColor',
            outlineOffset: 3,
            outlineColor: paper ? 'var(--t-bronze-d)' : 'var(--t-bronze-d)',
            padding:'14px 18px',
            background: paper ? 'rgba(235,226,207,0.4)' : 'rgba(10,16,32,0.5)'
          }}>
            <div style={{
              fontFamily:'var(--serif)', fontStyle:'italic', fontSize:11,
              color: paper ? 'var(--t-bronze-d)' : 'var(--t-bronze)',
              letterSpacing:'0.18em', textTransform:'lowercase',
              marginBottom:10, display:'flex', justifyContent:'space-between'
            }}>
              <span>praefatio · frontmatter</span>
              <span style={{fontFamily:'var(--mono)',fontStyle:'normal',fontSize:9,letterSpacing:'0.04em',color: paper ? '#6b6960' : 'var(--t-fg-faint)'}}>yaml</span>
            </div>
            <div style={{
              display:'grid', gridTemplateColumns:'120px 1fr', gap:'4px 16px',
              fontFamily:'var(--mono)', fontSize:11.5,
              color: paper ? 'var(--t-ink)' : 'var(--t-fg)'
            }}>
              {[
                ['uid', node.uid],
                ['type', <span><TypeDot type={node.type} size={7}/> {node.type}</span>],
                ['status', node.status || '—'],
                ['created', node.created],
                ['updated', node.updated],
                node.tags && ['tags', node.tags.map(t=>'#'+t).join(' ')],
                node.domains && ['domains', node.domains.join(', ')]
              ].filter(Boolean).map(([k,v],i)=>(
                <React.Fragment key={i}>
                  <span style={{color: paper ? '#6b6960' : 'var(--t-fg-mute)'}}>{k}</span>
                  <span style={{display:'flex', gap:6, alignItems:'center'}}>{v}</span>
                </React.Fragment>
              ))}
            </div>
          </div>

          {/* body — engraved book hand */}
          <div style={{
            fontFamily:'var(--body)', fontSize: paper ? 17 : 16,
            lineHeight:1.65, letterSpacing:'0.005em',
            color: paper ? 'var(--t-ink)' : 'var(--t-fg)',
            textWrap:'pretty'
          }}>
            <div style={{
              fontFamily:'var(--serif)', fontStyle:'italic', fontSize:11,
              color: paper ? 'var(--t-bronze-d)' : 'var(--t-bronze)',
              letterSpacing:'0.18em', textTransform:'lowercase',
              marginBottom:14
            }}>corpus · body</div>
            {node.body.split('\n\n').map((p,i)=>(
              <p key={i} style={{margin:'0 0 14px'}}>
                {i===0 ? <span style={{
                  fontFamily:'var(--serif)', fontWeight:500,
                  fontSize:'3.6em', lineHeight:0.85, float:'left',
                  paddingRight:10, color: paper ? 'var(--terracotta)' : 'var(--t-bronze)'
                }}>{p[0]}</span> : null}
                {i===0 ? p.slice(1) : p}
              </p>
            ))}
          </div>
        </article>

        {/* relations rail */}
        <aside style={{
          borderLeft: paper ? '1px solid var(--t-paper-3)' : '1px solid var(--t-rule)',
          paddingLeft:24, position:'sticky', top:0, alignSelf:'start',
          fontFamily:'var(--sans)'
        }}>
          <div style={{
            fontFamily:'var(--serif)', fontStyle:'italic', fontSize:12,
            color: paper ? 'var(--t-bronze-d)' : 'var(--t-bronze)',
            letterSpacing:'0.18em', textTransform:'lowercase',
            marginBottom:14, display:'flex', justifyContent:'space-between', alignItems:'baseline'
          }}>
            <span>nexus · outbound</span>
            <span style={{fontFamily:'var(--mono)',fontStyle:'normal',fontSize:9,letterSpacing:'0.04em'}}>{related.length}</span>
          </div>

          {/* mini topology — radial relations */}
          <div style={{position:'relative', height:180, marginBottom:18}}>
            <svg width="100%" height="100%" viewBox="-100 -90 200 180" style={{overflow:'visible'}}>
              {/* center halo */}
              <circle cx="0" cy="0" r="22" fill={paper ? 'rgba(122,90,46,0.08)' : 'rgba(47,111,196,0.18)'}/>
              {/* edges */}
              {related.slice(0,6).map((r,i,arr) => {
                const a = (i / arr.length) * Math.PI * 2 - Math.PI/2;
                const x = Math.cos(a) * 70, y = Math.sin(a) * 65;
                return (
                  <g key={i}>
                    <line x1="0" y1="0" x2={x} y2={y}
                      stroke={TYPE_COLOR[r.target.type]} strokeWidth="1"
                      className="edge-flow" opacity="0.85"/>
                    <circle cx={x} cy={y} r="4" fill={TYPE_COLOR[r.target.type]}
                      stroke={paper ? 'var(--t-paper)' : 'var(--t-bg)'} strokeWidth="1"
                      style={{cursor:'pointer'}}
                      onClick={() => onOpen(r.target.uid)}/>
                    <text x={x} y={y + (y>0 ? 14 : -8)} textAnchor="middle"
                      fontFamily="var(--mono)" fontSize="7"
                      fill={paper ? '#6b6960' : 'var(--t-fg-mute)'}
                      letterSpacing="0.04em">
                      {r.target.title.length>16 ? r.target.title.slice(0,16)+'…' : r.target.title}
                    </text>
                  </g>
                );
              })}
              {/* center node */}
              <circle cx="0" cy="0" r="6" fill={TYPE_COLOR[node.type]}
                stroke={paper ? 'var(--t-paper)' : 'var(--t-bg)'} strokeWidth="1.5"/>
              <circle cx="0" cy="0" r="11" fill="none"
                stroke={paper ? 'var(--t-bronze-d)' : 'var(--t-bronze)'} strokeWidth="0.5" opacity="0.7"/>
            </svg>
          </div>

          {/* relation list */}
          <div style={{display:'flex', flexDirection:'column', gap:8}}>
            {related.map((r,i) => (
              <button key={i} onClick={() => onOpen(r.target.uid)}
                style={{
                  display:'flex', gap:8, alignItems:'flex-start', padding:'8px 0',
                  border:0, borderBottom: paper ? '0.5px dashed var(--t-paper-3)' : '0.5px dashed var(--t-rule)',
                  background:'transparent', color:'inherit', textAlign:'left',
                  cursor:'pointer', fontFamily:'var(--sans)', fontSize:12
                }}>
                <TypeDot type={r.target.type} size={7}/>
                <div style={{flex:1}}>
                  <div style={{fontFamily:'var(--mono)', fontSize:9, color:paper ? 'var(--t-bronze-d)' : 'var(--t-bronze)', letterSpacing:'0.06em', marginBottom:2}}>
                    — {r.type} —
                  </div>
                  <div style={{fontFamily:'var(--body)', fontSize:13, color: paper ? 'var(--t-ink)' : 'var(--t-fg)'}}>
                    {r.target.title}
                  </div>
                </div>
              </button>
            ))}
          </div>

          {inbound.length > 0 && (
            <>
              <div style={{
                fontFamily:'var(--serif)', fontStyle:'italic', fontSize:12,
                color: paper ? 'var(--t-bronze-d)' : 'var(--t-bronze)',
                letterSpacing:'0.18em', textTransform:'lowercase',
                margin:'24px 0 10px'
              }}>← nexus inbound</div>
              <div style={{display:'flex', flexDirection:'column', gap:6, fontSize:12}}>
                {inbound.slice(0,4).map((r,i) => (
                  <button key={i} onClick={() => onOpen(r.from.uid)} style={{
                    display:'flex', gap:8, padding:'4px 0', alignItems:'center',
                    border:0, background:'transparent', color:'inherit', textAlign:'left', cursor:'pointer'
                  }}>
                    <TypeDot type={r.from.type} size={7}/>
                    <span style={{fontFamily:'var(--body)', fontSize:12, flex:1}}>{r.from.title}</span>
                    <span style={{fontFamily:'var(--mono)', fontSize:9, color: paper ? 'var(--t-bronze-d)' : 'var(--t-bronze)'}}>{r.type}</span>
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

// ─────────────────────────────────────────────────────────
// Command palette — sextant
// ─────────────────────────────────────────────────────────
function CommandPalette({ open, onClose, vault, onOpen }) {
  const [q, setQ] = React.useState("");
  const ref = React.useRef();
  React.useEffect(() => { if (open && ref.current) ref.current.focus(); }, [open]);
  if (!open) return null;
  const results = q
    ? vault.filter(n => n.title.toLowerCase().includes(q.toLowerCase()) || n.uid.includes(q)).slice(0,7)
    : vault.slice(0,7);

  return (
    <div onClick={onClose} style={{
      position:'absolute', inset:0, zIndex:50,
      background:'rgba(6,9,20,0.65)',
      backdropFilter:'blur(4px)',
      display:'flex', justifyContent:'center', paddingTop:'10vh'
    }}>
      <div onClick={e => e.stopPropagation()} style={{
        width:560, maxHeight:'70vh', background:'rgba(10,16,32,0.92)',
        backdropFilter:'blur(20px)',
        border:'1px solid var(--t-bronze-d)',
        outline:'0.5px solid var(--t-bronze-d)',
        outlineOffset:3,
        position:'relative', display:'flex', flexDirection:'column'
      }}>
        {/* corner reticles */}
        <span style={{position:'absolute', top:-1, left:-1, width:10, height:10, borderTop:'1px solid var(--t-bronze)', borderLeft:'1px solid var(--t-bronze)'}}/>
        <span style={{position:'absolute', top:-1, right:-1, width:10, height:10, borderTop:'1px solid var(--t-bronze)', borderRight:'1px solid var(--t-bronze)'}}/>
        <span style={{position:'absolute', bottom:-1, left:-1, width:10, height:10, borderBottom:'1px solid var(--t-bronze)', borderLeft:'1px solid var(--t-bronze)'}}/>
        <span style={{position:'absolute', bottom:-1, right:-1, width:10, height:10, borderBottom:'1px solid var(--t-bronze)', borderRight:'1px solid var(--t-bronze)'}}/>

        <div style={{
          padding:'10px 18px 0', display:'flex', alignItems:'baseline', gap:10,
          fontFamily:'var(--serif)', fontStyle:'italic', fontSize:11,
          color:'var(--t-bronze)', letterSpacing:'0.18em', textTransform:'lowercase'
        }}>
          <span>praeceptum · command</span>
          <span style={{flex:1, height:0, borderTop:'0.5px solid var(--t-bronze-d)'}}/>
          <span style={{fontFamily:'var(--mono)', fontStyle:'normal', fontSize:9, color:'var(--t-fg-faint)', letterSpacing:'0.04em'}}>
            esc to close
          </span>
        </div>

        <div style={{padding:'4px 18px 14px', borderBottom:'1px solid var(--t-rule)'}}>
          <input ref={ref} value={q} onChange={e => setQ(e.target.value)}
            placeholder="search vault — title, tag, :type, uid"
            className="t-input"
            style={{fontSize:20}}/>
        </div>

        <div style={{flex:1, overflowY:'auto', padding:'6px 0'}}>
          {results.map((n,i) => (
            <button key={n.uid} onClick={() => { onOpen(n.uid); onClose(); }}
              style={{
                display:'grid', gridTemplateColumns:'18px 1fr auto auto',
                alignItems:'center', gap:14, padding:'8px 18px',
                border:0,
                background: i===0 ? 'rgba(201,168,106,0.10)' : 'transparent',
                color:'var(--t-fg)', textAlign:'left', width:'100%',
                cursor:'pointer', fontFamily:'var(--sans)', fontSize:13,
                position:'relative'
              }}>
              {i===0 && <span style={{position:'absolute',left:0,top:0,bottom:0,width:2,background:'var(--t-bronze)'}}/>}
              <TypeDot type={n.type} size={8}/>
              <span style={{fontFamily:'var(--body)',fontSize:14}}>{n.title}</span>
              <span style={{fontFamily:'var(--serif)',fontStyle:'italic',fontSize:10,color:'var(--t-bronze)',letterSpacing:'0.06em'}}>{n.type}</span>
              <span style={{fontFamily:'var(--mono)',fontSize:10,color:'var(--t-fg-faint)',letterSpacing:'0.04em'}}>{n.uid}</span>
            </button>
          ))}
        </div>

        <div style={{
          padding:'8px 18px', borderTop:'1px solid var(--t-rule)',
          display:'flex', gap:18, fontFamily:'var(--mono)', fontSize:9,
          color:'var(--t-fg-mute)', letterSpacing:'0.06em', textTransform:'uppercase'
        }}>
          <span>↑↓ <span style={{color:'var(--t-fg-faint)'}}>navigate</span></span>
          <span>⏎ <span style={{color:'var(--t-fg-faint)'}}>open</span></span>
          <span>⌘⏎ <span style={{color:'var(--t-fg-faint)'}}>open in topology</span></span>
          <span style={{marginLeft:'auto',fontFamily:'var(--serif)',fontStyle:'italic',fontSize:10,letterSpacing:'0.18em',textTransform:'lowercase',color:'var(--t-bronze)'}}>
            {results.length} resultata
          </span>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────
// Composer — stele on which you carve a new locus
// ─────────────────────────────────────────────────────────
function Composer({ onBack, paper }) {
  const [type, setType] = React.useState('document');
  const [title, setTitle] = React.useState('');
  const [body, setBody] = React.useState('');
  const [tags, setTags] = React.useState(['design-doc','architecture']);

  const types = ["project","task","document","entity","conversation","article","bookmark","procedure","topic","event"];

  return (
    <div className={`canvas ${paper ? 'paper' : ''}`} style={{display:'flex', flexDirection:'column'}}>
      <Meridian visible={!paper}/>
      <Reticle/>
      <Corners
        tl={{label:'componere · new locus', value:'untitled'}}
        tr={{label:'genus · type', value: type}}
        bl={{label:'caret', value: `ln 1 · col ${title.length}`}}
        br={{label:'auto-uid', value:'pending'}}
      />

      <HeaderStrip
        label="Compose"
        latin="componere · novum locum"
        telemetry={<>type <b>{type}</b> · uid <b>pending</b> · saved <b>—</b></>}
        right={
          <div style={{display:'flex', gap:8}}>
            <button className="t-btn" onClick={onBack} style={{padding:'5px 12px',fontSize:12}}>cancel <span className="key">esc</span></button>
            <button className="t-btn solid" style={{padding:'5px 12px',fontSize:12}}>save <span className="key">⌘S</span></button>
          </div>
        }
      />

      <div style={{flex:1, overflowY:'auto', display:'grid', gridTemplateColumns:'1fr 280px', gap:32, padding:'40px 56px 56px'}}>
        <div style={{maxWidth:720}}>
          {/* type selector — bronze chip strip */}
          <div style={{display:'flex', alignItems:'center', gap:6, marginBottom:18, flexWrap:'wrap'}}>
            <span className="smcaps" style={{color: paper ? 'var(--t-bronze-d)' : 'var(--t-bronze)'}}>genus —</span>
            {types.map(t => (
              <button key={t} onClick={()=>setType(t)}
                style={{
                  border:'0.5px solid', borderColor: type===t ? 'var(--t-bronze)' : 'transparent',
                  background: type===t ? 'rgba(201,168,106,0.10)' : 'transparent',
                  color: paper ? 'var(--t-ink)' : 'var(--t-fg)',
                  fontFamily:'var(--mono)', fontSize:10, padding:'4px 10px',
                  letterSpacing:'0.04em', cursor:'pointer', display:'flex', alignItems:'center', gap:5
                }}>
                <TypeDot type={t} size={6}/>{t}
              </button>
            ))}
          </div>

          <input value={title} onChange={e=>setTitle(e.target.value)}
            placeholder="title — titulus"
            style={{
              border:0, borderBottom:`1px solid ${paper ? 'var(--t-bronze-d)' : 'var(--t-bronze-d)'}`,
              background:'transparent', outline:'none', width:'100%',
              fontFamily:'var(--serif)', fontWeight:500,
              fontSize:42, lineHeight:1.1, color: paper ? 'var(--t-ink)' : 'var(--t-fg)',
              padding:'4px 0 16px', marginBottom:24, letterSpacing:'-0.005em'
            }}/>

          {/* tag row */}
          <div style={{display:'flex', alignItems:'center', gap:6, marginBottom:24}}>
            <span className="smcaps" style={{color: paper ? 'var(--t-bronze-d)' : 'var(--t-bronze)'}}>lemmata —</span>
            {tags.map(t => (
              <span key={t} className="t-chip" style={{cursor:'pointer'}}>
                #{t} <span style={{opacity:0.5,marginLeft:2}}>×</span>
              </span>
            ))}
            <button style={{
              border:'0.5px dashed var(--t-bronze-d)', background:'transparent',
              color:'var(--t-bronze)', fontFamily:'var(--mono)', fontSize:10,
              padding:'3px 10px', letterSpacing:'0.04em', cursor:'pointer'
            }}>+ add lemma</button>
          </div>

          {/* body editor */}
          <div style={{
            border: paper ? '0.5px solid var(--t-bronze-d)' : '0.5px solid var(--t-bronze-d)',
            outline: paper ? '0.5px solid var(--t-bronze-d)' : '0.5px solid var(--t-bronze-d)',
            outlineOffset:3,
            padding:'18px 22px', background: paper ? 'rgba(255,250,238,0.5)' : 'rgba(10,16,32,0.5)',
            position:'relative'
          }}>
            <div style={{
              position:'absolute', top:-8, left:18, padding:'0 8px',
              background: paper ? 'var(--t-paper)' : 'var(--t-bg)',
              fontFamily:'var(--serif)', fontStyle:'italic', fontSize:11,
              color: paper ? 'var(--t-bronze-d)' : 'var(--t-bronze)',
              letterSpacing:'0.18em', textTransform:'lowercase'
            }}>corpus · body</div>
            <textarea value={body} onChange={e=>setBody(e.target.value)}
              placeholder="write the locus — markdown supported"
              style={{
                width:'100%', minHeight:280, border:0, outline:'none', resize:'vertical',
                background:'transparent',
                fontFamily:'var(--body)', fontSize:17, lineHeight:1.65,
                color: paper ? 'var(--t-ink)' : 'var(--t-fg)',
                letterSpacing:'0.005em'
              }}/>
          </div>

          <div style={{
            marginTop:14, display:'flex', justifyContent:'space-between',
            fontFamily:'var(--mono)', fontSize:10, letterSpacing:'0.04em',
            color: paper ? '#6b6960' : 'var(--t-fg-mute)'
          }}>
            <span>{body.length} chars · {body.split(/\s+/).filter(Boolean).length} words</span>
            <span>autosave in <b style={{color: paper ? 'var(--t-ink)' : 'var(--t-fg)'}}>3s</b></span>
          </div>
        </div>

        {/* right rail — relations to add */}
        <aside style={{borderLeft: paper ? '1px solid var(--t-paper-3)' : '1px solid var(--t-rule)', paddingLeft:24}}>
          <div style={{
            fontFamily:'var(--serif)', fontStyle:'italic', fontSize:12,
            color: paper ? 'var(--t-bronze-d)' : 'var(--t-bronze)',
            letterSpacing:'0.18em', textTransform:'lowercase', marginBottom:12
          }}>nexus · suggested</div>

          <div style={{display:'flex', flexDirection:'column', gap:8, fontSize:12}}>
            {[
              ['belongs-to', 'project', 'Loci', 'a1b2c3d4'],
              ['relates-to', 'topic', 'Graph databases', '12fe44a0'],
              ['mentions', 'article', 'Attention is all you need', 'b6c80fde'],
              ['supports', 'procedure', 'Daily review — vault hygiene', '10ee5503'],
            ].map(([rel, t, name, uid],i) => (
              <button key={i} style={{
                border:0, borderBottom: paper ? '0.5px dashed var(--t-paper-3)' : '0.5px dashed var(--t-rule)',
                background:'transparent', color:'inherit', textAlign:'left', cursor:'pointer',
                padding:'8px 0', display:'grid', gridTemplateColumns:'14px 1fr',
                gap:8, alignItems:'flex-start'
              }}>
                <TypeDot type={t} size={7}/>
                <div>
                  <div style={{fontFamily:'var(--mono)',fontSize:9,color: paper?'var(--t-bronze-d)':'var(--t-bronze)',letterSpacing:'0.06em',marginBottom:2}}>— {rel} —</div>
                  <div style={{fontFamily:'var(--body)',fontSize:13,color: paper?'var(--t-ink)':'var(--t-fg)'}}>{name}</div>
                  <div style={{fontFamily:'var(--mono)',fontSize:9,color: paper?'#6b6960':'var(--t-fg-faint)',letterSpacing:'0.04em',marginTop:1}}>{uid}</div>
                </div>
              </button>
            ))}
          </div>
        </aside>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────
// Empty state — blank star chart
// ─────────────────────────────────────────────────────────
function EmptyState({ onCompose }) {
  return (
    <div className="canvas" style={{display:'flex', flexDirection:'column'}}>
      <Meridian/>
      <Reticle/>
      <Corners
        tl={{label:'thesaurus', value:'0 nodi · 0 nexus'}}
        tr={{label:'status', value:'vacuum'}}
        bl={{label:'last', value:'never'}}
        br={{label:'fol.', value:'0/0'}}
      />

      <div style={{flex:1, display:'grid', placeItems:'center', position:'relative'}}>
        {/* central empty bezel */}
        <div style={{position:'relative'}}>
          <Bezel size={340} items={['attendere','nullum','adhuc','vacuum']}/>

          <div style={{
            position:'absolute', top:'50%', left:'50%',
            transform:'translate(-50%, -50%)',
            textAlign:'center', maxWidth:280
          }}>
            <div style={{
              fontFamily:'var(--serif)', fontStyle:'italic', fontSize:11,
              color:'var(--t-bronze)', letterSpacing:'0.34em', textTransform:'lowercase',
              marginBottom:14
            }}>vacuum · empty</div>
            <h2 className="h-section" style={{fontSize:26, marginBottom:12}}>
              The vault is <em>empty</em>.
            </h2>
            <p style={{
              fontFamily:'var(--body)', fontStyle:'italic',
              fontSize:14, lineHeight:1.55, color:'var(--t-fg-mute)',
              margin:'0 0 22px'
            }}>
              Save your first locus to begin.<br/>
              <span style={{fontStyle:'normal',fontFamily:'var(--mono)',fontSize:10,color:'var(--t-fg-faint)',letterSpacing:'0.04em'}}>
                — locus classicus —
              </span>
            </p>
            <button className="t-btn solid" onClick={onCompose}>
              compose first locus <span className="key">⌘N</span>
            </button>
          </div>
        </div>

        {/* scattered ghost nodes — what could be */}
        <svg style={{position:'absolute', inset:0, width:'100%', height:'100%', pointerEvents:'none'}} viewBox="0 0 800 500">
          {[
            [120,100,'project'],[680,90,'topic'],[80,400,'article'],
            [720,420,'task'],[140,260,'bookmark'],[660,260,'document']
          ].map(([x,y,t],i)=>(
            <g key={i} opacity="0.18">
              <circle cx={x} cy={y} r="5" fill={TYPE_COLOR[t]}/>
              <text x={x} y={y+18} textAnchor="middle"
                fontFamily="var(--mono)" fontSize="7" fill="var(--t-fg-faint)" letterSpacing="0.04em">
                {t}?
              </text>
            </g>
          ))}
          {/* dotted connecting lines from center */}
          <g stroke="var(--t-bronze-d)" strokeDasharray="1 4" strokeWidth="0.5" opacity="0.3">
            <line x1="400" y1="250" x2="120" y2="100"/>
            <line x1="400" y1="250" x2="680" y2="90"/>
            <line x1="400" y1="250" x2="80"  y2="400"/>
            <line x1="400" y1="250" x2="720" y2="420"/>
          </g>
        </svg>
      </div>

      <div style={{
        padding:'14px 24px', borderTop:'1px solid var(--t-rule-soft)',
        display:'flex', justifyContent:'space-between',
        fontFamily:'var(--mono)', fontSize:10, color:'var(--t-fg-mute)', letterSpacing:'0.04em'
      }}>
        <span>or — <span style={{color:'var(--t-bronze)'}}>capture</span> via mcp · cli · drag-drop</span>
        <span>see <span style={{color:'var(--t-bronze)'}}>capture flow</span> for guidance</span>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────
// Settings — calibration panel
// ─────────────────────────────────────────────────────────
function SettingsScreen() {
  const stats = [
    { label: 'loci · total',     latin: 'numero',     value: '17',   sub: '+3 this week' },
    { label: 'nexus · edges',    latin: 'nexus',      value: '23',   sub: 'avg 1.4/locus' },
    { label: 'orphans',          latin: 'solitarii',  value: '2',    sub: 'sourdough cluster' },
    { label: 'drift · stale',    latin: 'fluctus',    value: '4',    sub: '> 30 days untouched' },
    { label: 'untyped',          latin: 'incognitae', value: '0',    sub: 'all classified' },
    { label: 'asset registry',   latin: 'res',        value: '12',   sub: '3 unresolved' },
  ];

  return (
    <div className="canvas" style={{display:'flex', flexDirection:'column'}}>
      <Meridian/>
      <Corners
        tl={{label:'calibratio', value:'vault settings'}}
        tr={{label:'vault', value:'~/Nextcloud/loci'}}
        bl={{label:'last sync', value:'2026-05-07 09:14'}}
        br={{label:'engine', value:'networkx 3.2 · v0.4'}}
      />

      <HeaderStrip
        label="Calibration"
        latin="calibratio · vault health"
        telemetry={<>vault healthy · drift <b>4</b> · orphans <b>2</b></>}
        right={<button className="t-btn" style={{padding:'5px 12px',fontSize:12}}>re-index <span className="key">⌘R</span></button>}
      />

      <div style={{flex:1, overflowY:'auto', padding:'40px 48px'}}>
        {/* health stats grid */}
        <div style={{
          display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:20, marginBottom:40
        }}>
          {stats.map(s => (
            <div key={s.label} className="frame bronze-frame" style={{padding:'18px 20px'}}>
              <div style={{
                fontFamily:'var(--serif)', fontStyle:'italic', fontSize:10,
                color:'var(--t-bronze)', letterSpacing:'0.18em', textTransform:'lowercase',
                marginBottom:6, display:'flex', justifyContent:'space-between'
              }}>
                <span>{s.label}</span>
                <span style={{color:'var(--t-bronze-d)'}}>— {s.latin}</span>
              </div>
              <div style={{
                fontFamily:'var(--serif)', fontWeight:500, fontSize:42,
                lineHeight:1, color:'var(--t-fg)', letterSpacing:'-0.01em'
              }}>{s.value}</div>
              <div style={{
                marginTop:6, fontFamily:'var(--mono)', fontSize:10,
                color:'var(--t-fg-mute)', letterSpacing:'0.04em'
              }}>{s.sub}</div>
            </div>
          ))}
        </div>

        {/* type distribution bar */}
        <div className="frame bronze-frame" style={{padding:'18px 22px', marginBottom:30}}>
          <div style={{
            fontFamily:'var(--serif)', fontStyle:'italic', fontSize:11,
            color:'var(--t-bronze)', letterSpacing:'0.18em', textTransform:'lowercase',
            marginBottom:14, display:'flex', justifyContent:'space-between'
          }}>
            <span>genera · type distribution</span>
            <span style={{fontFamily:'var(--mono)',fontStyle:'normal',fontSize:9,color:'var(--t-fg-faint)',letterSpacing:'0.04em'}}>17 nodes</span>
          </div>
          <div style={{display:'flex', height:14, marginBottom:12, overflow:'hidden'}}>
            {[
              ['project',2],['task',1],['document',1],['entity',1],
              ['conversation',1],['article',2],['bookmark',1],['procedure',2],
              ['topic',4],['event',1],['default',1]
            ].map(([t,n],i)=>(
              <div key={i} title={`${t}: ${n}`} style={{
                flex:n, background:`var(--type-${t})`, opacity:0.85,
                borderRight: i<10 ? '0.5px solid var(--t-bg)' : 0
              }}/>
            ))}
          </div>
          <div style={{
            display:'flex', gap:14, flexWrap:'wrap',
            fontFamily:'var(--mono)', fontSize:10,
            color:'var(--t-fg-mute)', letterSpacing:'0.04em'
          }}>
            {[
              ['topic',4],['project',2],['article',2],['procedure',2],
              ['task',1],['document',1],['entity',1],['conversation',1],
              ['bookmark',1],['event',1]
            ].map(([t,n],i)=>(
              <span key={i} style={{display:'flex', alignItems:'center', gap:5}}>
                <TypeDot type={t} size={6}/>{t} <b style={{color:'var(--t-fg)'}}>{n}</b>
              </span>
            ))}
          </div>
        </div>

        {/* ratio panel — preferences laid out as engraved switches */}
        <div className="frame bronze-frame" style={{padding:'18px 22px'}}>
          <div style={{
            fontFamily:'var(--serif)', fontStyle:'italic', fontSize:11,
            color:'var(--t-bronze)', letterSpacing:'0.18em', textTransform:'lowercase',
            marginBottom:18
          }}>ratio · preferences</div>

          {[
            ['Auto-classify on capture',     'classifier · auto',     true],
            ['Suggest nexus while composing','nexus · suggestor',     true],
            ['Surface orphans in sidebar',   'solitarii · in oculo',  false],
            ['Roman numeral folio counters', 'numeri romani',         true],
            ['Latin twin labels',            'lingua latina · ubique',true],
          ].map(([label, latin, on],i) => (
            <div key={i} style={{
              display:'flex', alignItems:'center', gap:14,
              padding:'10px 0',
              borderTop: i>0 ? '0.5px dashed var(--t-rule)' : 0
            }}>
              <div style={{flex:1}}>
                <div style={{fontFamily:'var(--body)', fontSize:14, color:'var(--t-fg)'}}>{label}</div>
                <div style={{fontFamily:'var(--serif)', fontStyle:'italic', fontSize:10, color:'var(--t-bronze)', letterSpacing:'0.06em', marginTop:2}}>— {latin}</div>
              </div>
              <div style={{
                width:36, height:18, borderRadius:0,
                border:'0.5px solid var(--t-bronze-d)',
                background: on ? 'var(--t-bronze)' : 'transparent',
                position:'relative', cursor:'pointer'
              }}>
                <div style={{
                  position:'absolute', top:1, [on?'right':'left']:1, bottom:1,
                  width:14, background: on ? 'var(--t-bg)' : 'var(--t-bronze-d)',
                  transition:'all 200ms ease'
                }}/>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

Object.assign(window, {
  TYPE_COLOR,
  SplashScreen, VaultRail, VaultIndex, NodeDetail, CommandPalette,
  Composer, EmptyState, SettingsScreen
});
