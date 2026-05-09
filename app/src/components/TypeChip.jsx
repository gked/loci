import { TypeDot } from "./TypeDot.jsx";

export function TypeChip({ type }) {
  return (
    <span style={{
      display: "inline-flex",
      alignItems: "center",
      gap: 6,
      padding: "3px 10px",
      borderRadius: 999,
      fontSize: 12,
      fontWeight: 500,
      background: "var(--vault-sunken)",
      border: "1px solid var(--vault-rule)",
      color: "var(--vault-fg)",
    }}>
      <TypeDot type={type} size={8} />{type}
    </span>
  );
}
