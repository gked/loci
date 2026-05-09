export function HeaderStrip({ label, latin, telemetry, right }) {
  return (
    <div style={{
      display: "flex", alignItems: "baseline", gap: 14,
      padding: "14px 24px 12px",
      borderBottom: "1px solid var(--t-rule)",
      background: "rgba(6,9,20,0.65)",
      position: "relative", zIndex: 3, flexShrink: 0,
    }}>
      <div style={{ display: "flex", flexDirection: "column", lineHeight: 1 }}>
        <span style={{
          fontFamily: "var(--font-display)", fontWeight: 500, fontSize: 18,
          color: "var(--t-fg)", letterSpacing: "0.01em",
        }}>{label}</span>
        {latin && (
          <span className="latin-twin" style={{ marginTop: 3 }}>— {latin} —</span>
        )}
      </div>
      {telemetry && <span className="tel">{telemetry}</span>}
      <div style={{ marginLeft: "auto" }}>{right}</div>
    </div>
  );
}
