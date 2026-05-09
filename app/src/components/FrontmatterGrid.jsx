import { Fragment } from "react";
import { TypeDot } from "./TypeDot.jsx";

export function FrontmatterGrid({ node }) {
  const rows = [
    ["uid", node.uid, "mono"],
    ["type", node.type, "type"],
    ["created", node.created_at, "mono"],
    ["updated", node.updated_at, "mono"],
    ["status", node.status],
    ...(node.tags?.length ? [["tags", node.tags.map(t => "#" + t).join(" ")]] : []),
    ...(node.domains?.length ? [["domains", node.domains.join(", ")]] : []),
  ].filter(([, v]) => v);

  return (
    <div style={{
      background: "var(--vault-sunken)", borderRadius: 6, padding: "12px 14px",
      display: "grid", gridTemplateColumns: "100px 1fr", gap: "6px 14px",
      fontFamily: "var(--font-mono)", fontSize: 12,
    }}>
      {rows.map(([k, v, mode], i) => (
        <Fragment key={i}>
          <span style={{ color: "var(--vault-fg-muted)" }}>{k}</span>
          <span style={{ color: "var(--vault-fg)", display: "flex", alignItems: "center", gap: 6 }}>
            {mode === "type" && <TypeDot type={v} />}
            {v}
          </span>
        </Fragment>
      ))}
    </div>
  );
}
