export function Corners({ tl, tr, bl, br }) {
  const Cell = (pos, p) => p ? (
    <div className={`corner ${pos}`}>
      {p.label && <i>{p.label}</i>}
      {p.value && <b>{p.value}</b>}
    </div>
  ) : null;
  return <>{Cell("tl", tl)}{Cell("tr", tr)}{Cell("bl", bl)}{Cell("br", br)}</>;
}
