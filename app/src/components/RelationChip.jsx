export function RelationChip({ children }) {
  return (
    <span style={{
      fontFamily: "var(--font-mono)",
      fontSize: 11,
      padding: "3px 8px",
      background: "#fff",
      border: "1px solid var(--vault-rule)",
      borderRadius: 3,
      color: "var(--vault-fg-muted)",
    }}>
      {children}
    </span>
  );
}
