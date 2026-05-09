// Atoms — shared topology-vibe primitives.

const ROMAN = ["I","II","III","IV","V","VI","VII","VIII","IX","X","XI","XII","XIII","XIV","XV","XVI","XVII","XVIII","XIX","XX","XXI","XXII","XXIII"];
const toRoman = (n) => ROMAN[n-1] || String(n);

// Latin twins for common UI labels
const LATIN = {
  "all loci": "omnia loca",
  "recent": "recentia",
  "graph": "topologia",
  "topology": "topologia",
  "inbox": "ingressus",
  "settings": "calibratio",
  "vault": "thesaurus",
  "save": "servare",
  "open": "aperire",
  "new": "novum",
  "search": "quaerere",
  "compose": "componere",
  "tag": "lemma",
  "tags": "lemmata",
  "relations": "nexus",
  "relation": "nexus",
  "frontmatter": "praefatio",
  "body": "corpus",
  "uid": "indicium",
  "type": "genus",
  "types": "genera",
  "created": "natum",
  "updated": "renovatum",
  "status": "status",
  "domains": "dominia",
  "splash": "ianua",
  "node": "locus",
  "nodes": "loci",
  "empty": "vacuum",
  "health": "valetudo",
  "drift": "fluctus",
  "stale": "obsoletum",
};

const T_LATIN = {
  project: "negotium", task: "labor", document: "documentum", entity: "persona",
  conversation: "colloquium", article: "articulus", bookmark: "signum",
  procedure: "ratio", topic: "argumentum", event: "eventus", asset: "res", default: "ignotum",
};

// Engraved corner annotations
function Corners({ tl, tr, bl, br }) {
  const Cell = (pos, p) => p ? (
    <div className={`corner ${pos}`}>
      {p.label && <i>{p.label}</i>}
      {p.value && <b>{p.value}</b>}
      {p.sub && <span className="faint" style={{fontSize:8.5,letterSpacing:'0.06em'}}>{p.sub}</span>}
    </div>
  ) : null;
  return <>{Cell('tl', tl)}{Cell('tr', tr)}{Cell('bl', bl)}{Cell('br', br)}</>;
}

// Reticle bracket overlay
function Reticle() { return <div className="reticle"><i/></div>; }

// Dotted meridian crosshairs
function Meridian({ visible = true }) { return visible ? <div className="meridian"/> : null; }

// Type dot
function TypeDot({ type, size = 8, halo = false }) {
  const color = `var(--type-${type || 'default'})`;
  return (
    <span
      className={halo ? 't-dot t-halo' : 't-dot'}
      data-type={type}
      style={{ width: size, height: size, color }}
    />
  );
}

// Roman numeral page indicator
function RomanIndex({ idx, of }) {
  return (
    <div style={{
      position: 'absolute', top: 14, left: '50%', transform: 'translateX(-50%)',
      fontFamily: 'var(--serif)', fontSize: 11, color: 'var(--t-bronze)',
      letterSpacing: '0.18em', textTransform: 'lowercase', fontStyle: 'italic',
      zIndex: 4
    }}>
      <span style={{color:'var(--t-bronze-d)'}}>fol.</span> {toRoman(idx)} <span style={{color:'var(--t-bronze-d)'}}>·</span> <span style={{fontStyle:'normal',fontFamily:'var(--mono)',fontSize:10,color:'var(--t-fg-faint)',letterSpacing:'0.04em'}}>{idx}/{of}</span>
    </div>
  );
}

// Latin twin under a label
function L({ children, latin, hideLatin }) {
  const k = String(children).toLowerCase().trim();
  const twin = latin || LATIN[k];
  return (
    <span style={{display:'inline-flex', flexDirection:'column', lineHeight: 1.05}}>
      <span>{children}</span>
      {twin && !hideLatin && <span className="latin-twin">{twin}</span>}
    </span>
  );
}

// Bezel — bronze ring engraved with Latin
function Bezel({ size = 320, items = ["nodi","nexus","loci","via"], rotate = false }) {
  const r = size/2 - 14;
  const r2 = r - 4;
  // duplicate items along path
  const top = items.slice(0, Math.ceil(items.length/2)).join(" · ");
  const bot = items.slice(Math.ceil(items.length/2)).join(" · ");
  return (
    <svg width={size} height={size} viewBox={`-${size/2} -${size/2} ${size} ${size}`} style={{ overflow: 'visible' }}>
      <g className={rotate ? 'bezel-rotate' : ''}>
        <circle r={r}  fill="none" stroke="var(--t-bronze-d)" strokeWidth="0.6" opacity="0.7"/>
        <circle r={r2} fill="none" stroke="var(--t-bronze-d)" strokeWidth="0.4" opacity="0.5"/>
        <path id="bezel-top" d={`M ${-r+4},0 A ${r-4},${r-4} 0 0,1 ${r-4},0`} fill="none"/>
        <path id="bezel-bot" d={`M ${r-4},0 A ${r-4},${r-4} 0 0,1 ${-r+4},0`} fill="none"/>
        <text fontFamily="var(--serif)" fontStyle="italic" fontSize="11" fill="var(--t-bronze)" letterSpacing="0.18em" textTransform="lowercase">
          <textPath href="#bezel-top" startOffset="50%" textAnchor="middle">{top}</textPath>
        </text>
        <text fontFamily="var(--serif)" fontStyle="italic" fontSize="11" fill="var(--t-bronze)" letterSpacing="0.18em" textTransform="lowercase">
          <textPath href="#bezel-bot" startOffset="50%" textAnchor="middle">{bot}</textPath>
        </text>
        {/* cardinal marks N E S W */}
        <g fontFamily="var(--serif)" fontSize="11" fill="var(--t-bronze)">
          <text y={-r+10} textAnchor="middle">N</text>
          <text x={r-10} y={3.5}>E</text>
          <text y={r-2} textAnchor="middle">S</text>
          <text x={-r+10} y={3.5} textAnchor="end">W</text>
        </g>
        {/* hairline meridians */}
        <line x1="0" y1={-r2} x2="0" y2={r2} stroke="var(--t-bronze)" strokeWidth="0.4" strokeDasharray="1 4" opacity="0.5"/>
        <line x1={-r2} y1="0" x2={r2} y2="0" stroke="var(--t-bronze)" strokeWidth="0.4" strokeDasharray="1 4" opacity="0.5"/>
      </g>
    </svg>
  );
}

// Header strip used at top of every screen — like an instrument label plate
function HeaderStrip({ label, latin, telemetry, right }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'baseline', gap: 14,
      padding: '14px 24px 12px',
      borderBottom: '1px solid var(--t-rule)',
      background: 'rgba(6,9,20,0.65)',
      position: 'relative', zIndex: 3
    }}>
      <div style={{display:'flex', flexDirection:'column', lineHeight:1}}>
        <span style={{
          fontFamily:'var(--serif)', fontWeight:500, fontSize:18, color:'var(--t-fg)',
          letterSpacing:'0.01em'
        }}>{label}</span>
        {latin && <span className="latin-twin" style={{marginTop:3}}>— {latin} —</span>}
      </div>
      {telemetry && <span className="tel">{telemetry}</span>}
      <div style={{marginLeft:'auto'}}>{right}</div>
    </div>
  );
}

Object.assign(window, {
  ROMAN, toRoman, LATIN, T_LATIN,
  Corners, Reticle, Meridian, TypeDot, RomanIndex, L, Bezel, HeaderStrip
});
