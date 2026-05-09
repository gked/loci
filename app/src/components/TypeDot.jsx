export function TypeDot({ type, size = 8, halo = false }) {
  const style = size !== 8 ? { width: size, height: size } : undefined;
  return (
    <span
      className={halo ? "t-dot t-halo" : "t-dot"}
      data-type={type}
      style={style}
    />
  );
}
