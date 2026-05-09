import { TypeDot } from "./TypeDot.jsx";

export function NodeRow({ node, selected, onClick }) {
  return (
    <button onClick={onClick} style={{
      display: "flex", alignItems: "center", gap: 12, padding: "8px 14px",
      border: 0, background: selected ? "var(--vault-sunken)" : "transparent",
      borderBottom: "1px solid var(--vault-rule)", textAlign: "left",
      width: "100%", cursor: "pointer", fontFamily: "var(--font-sans)",
    }}>
      <TypeDot type={node.type} />
      <span style={{ flex: 1, fontSize: 13, color: "var(--vault-fg)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
        {node.title}
      </span>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--vault-fg-faint)" }}>
        {node.uid}
      </span>
    </button>
  );
}
