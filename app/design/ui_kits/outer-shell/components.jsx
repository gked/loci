// Outer-shell components — classical register.
const Plate = ({ children, style }) => (
  <div className="plate" style={style}>
    <div className="plate-inner">{children}</div>
  </div>
);

const Wordmark = ({ size = 88, color = "var(--lampblack)" }) => (
  <div style={{ fontFamily: "var(--font-display)", fontWeight: 500, fontSize: size, lineHeight: 1, letterSpacing: "-0.01em", color, display: "inline-flex", alignItems: "baseline" }}>
    <span>L</span>
    <span style={{ display: "inline-block", width: size * 0.07, height: size * 0.07, background: "var(--terracotta)", borderRadius: "50%", margin: `0 ${size * 0.012}px`, alignSelf: "center", transform: `translateY(${size * 0.18}px)` }}/>
    <span>oci</span>
  </div>
);

const Monogram = ({ size = 80 }) => (
  <img src="../../assets/logo/monogram.svg" alt="" width={size} height={size} />
);

const Seal = ({ size = 140 }) => (
  <img src="../../assets/logo/seal.svg" alt="" width={size} height={size} />
);

const MeanderRule = ({ width = "100%" }) => (
  <div style={{ width, height: 32, backgroundImage: `url(../../assets/motifs/meander.svg)`, backgroundRepeat: "repeat-x", backgroundSize: "auto 32px", opacity: 0.85 }} />
);

const SmallCaps = ({ children, color = "var(--bronze)" }) => (
  <span style={{ fontFamily: "var(--font-serif)", fontFeatureSettings: '"smcp" 1, "c2sc" 1', textTransform: "lowercase", letterSpacing: "0.18em", fontSize: 11, color }}>
    {children}
  </span>
);

const RomanNumeral = ({ children, color = "var(--terracotta)" }) => (
  <span style={{ fontFamily: "var(--font-display)", fontStyle: "italic", color, fontSize: "1.1em" }}>{children}</span>
);

const SectionHeader = ({ numeral, overline, title }) => (
  <div style={{ display: "flex", alignItems: "baseline", gap: 16, marginBottom: 16 }}>
    {numeral && <RomanNumeral>{numeral}.</RomanNumeral>}
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {overline && <SmallCaps>{overline}</SmallCaps>}
      <h2 style={{ fontFamily: "var(--font-display)", fontWeight: 500, fontSize: 40, lineHeight: 1.15, color: "var(--lampblack)", margin: 0 }}>{title}</h2>
    </div>
  </div>
);

const OButton = ({ variant = "primary", children, onClick }) => {
  const styles = {
    primary: { background: "var(--terracotta)", color: "var(--ivory)", border: "1px solid var(--terracotta)" },
    secondary: { background: "transparent", color: "var(--ink)", border: "1px solid var(--ink)" },
    ghost: { background: "transparent", color: "var(--ink)", border: "1px solid transparent" }
  };
  return (
    <button onClick={onClick} style={{ ...styles[variant], padding: "10px 22px", borderRadius: 0, fontFamily: "var(--font-serif)", fontSize: 15, fontWeight: 500, letterSpacing: "0.04em", cursor: "pointer", transition: "opacity 120ms" }}
      onMouseEnter={e => e.currentTarget.style.opacity = 0.8}
      onMouseLeave={e => e.currentTarget.style.opacity = 1}>
      {children}
    </button>
  );
};

const DropCap = ({ children }) => (
  <p style={{ fontFamily: "var(--font-serif)", fontSize: 18, lineHeight: 1.6, fontFeatureSettings: '"onum" 1', textWrap: "pretty", margin: 0 }}>
    <span style={{ fontFamily: "var(--font-display)", fontSize: "3.6em", lineHeight: 0.85, float: "left", padding: "0.05em 12px 0 0", color: "var(--terracotta)", fontWeight: 600 }}>
      {String(children)[0]}
    </span>
    {String(children).slice(1)}
  </p>
);

Object.assign(window, { Plate, Wordmark, Monogram, Seal, MeanderRule, SmallCaps, RomanNumeral, SectionHeader, OButton, DropCap });
