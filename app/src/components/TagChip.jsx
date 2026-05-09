export function TagChip({ children }) {
  return (
    <span style={{
      fontSize: 11,
      color: "var(--vault-fg-muted)",
      fontFamily: "var(--font-mono)",
      padding: "2px 6px",
      background: "var(--vault-sunken)",
      borderRadius: 2,
    }}>
      #{children}
    </span>
  );
}
